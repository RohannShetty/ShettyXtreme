"""Sqlite FTS5 knowledge store (spec 4A §3.2).

`docs` (with real `title`/`body` columns) + `tags` + an external-content
FTS5 table kept in sync by triggers. `source_ref` is UNIQUE so ingest is
idempotent by brief_id; activation is the only status transition
(proposed -> activated, idempotent). All reads degrade on an empty store.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .schemas import KnowledgeDoc, SearchHit

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS docs (
    doc_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    source_ref TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    title TEXT,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT,
    activated_at TEXT
);
CREATE TABLE IF NOT EXISTS tags (
    doc_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    kind TEXT NOT NULL,
    PRIMARY KEY (doc_id, tag, kind)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
    title, body,
    content='docs', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON docs BEGIN
    INSERT INTO docs_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;
CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON docs BEGIN
    INSERT INTO docs_fts(docs_fts, rowid, title, body)
    VALUES ('delete', old.rowid, old.title, old.body);
END;
CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON docs BEGIN
    INSERT INTO docs_fts(docs_fts, rowid, title, body)
    VALUES ('delete', old.rowid, old.title, old.body);
    INSERT INTO docs_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;
"""


class DuplicateSourceError(Exception):
    """Raised when a source_ref already exists and replace=False."""


class KnowledgeStore:
    """Sqlite persistence for knowledge documents with FTS5 search."""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- projections --------------------------------------------------------

    @staticmethod
    def _title_from_payload(payload: dict) -> str:
        return str(payload.get("thesis", ""))[:200]

    @staticmethod
    def _body_from_payload(payload: dict) -> str:
        parts: list[str] = [
            str(payload.get("thesis", "")),
            str(payload.get("rationale", "")),
        ]
        for item in payload.get("evidence", []) or []:
            if isinstance(item, dict):
                parts.append(str(item.get("item", "")))
                parts.append(str(item.get("source", "")))
            else:
                parts.append(str(item))
        return " ".join(p for p in parts if p)

    def _tags_for(self, doc_ids: list[str]) -> dict[str, list[dict]]:
        if not doc_ids:
            return {}
        placeholders = ",".join("?" * len(doc_ids))
        rows = self._conn.execute(
            f"SELECT doc_id, tag, kind FROM tags WHERE doc_id IN ({placeholders}) ORDER BY rowid",
            doc_ids,
        ).fetchall()
        out: dict[str, list[dict]] = {}
        for doc_id, tag, kind in rows:
            out.setdefault(doc_id, []).append({"tag": tag, "kind": kind})
        return out

    @staticmethod
    def _row_to_doc(row: tuple, tags: list[dict]) -> KnowledgeDoc:
        doc_id, kind, source_ref, payload, status, created_at, activated_at = row
        return KnowledgeDoc(
            doc_id=doc_id,
            kind=kind,
            source_ref=source_ref,
            payload=json.loads(payload),
            status=status,
            created_at=created_at,
            activated_at=activated_at,
            tags=tags,
        )

    # -- writes -------------------------------------------------------------

    def ingest(self, doc: KnowledgeDoc, replace: bool = False) -> KnowledgeDoc:
        existing = self._conn.execute(
            "SELECT doc_id FROM docs WHERE source_ref = ?", (doc.source_ref,)
        ).fetchone()
        if existing is not None and not replace:
            raise DuplicateSourceError(doc.source_ref)
        if doc.created_at is None:
            doc = doc.model_copy(update={"created_at": datetime.now(UTC).isoformat()})
        if existing is not None:
            self._conn.execute("DELETE FROM docs WHERE source_ref = ?", (doc.source_ref,))
            self._conn.execute("DELETE FROM tags WHERE doc_id = ?", (existing[0],))
        self._conn.execute(
            "INSERT INTO docs (doc_id, kind, source_ref, payload, title, body, status, created_at, activated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc.doc_id,
                doc.kind,
                doc.source_ref,
                json.dumps(doc.payload),
                self._title_from_payload(doc.payload),
                self._body_from_payload(doc.payload),
                doc.status,
                doc.created_at,
                doc.activated_at,
            ),
        )
        for tag in doc.tags:
            self._conn.execute(
                "INSERT INTO tags (doc_id, tag, kind) VALUES (?, ?, ?)",
                (doc.doc_id, str(tag.get("tag", "")), str(tag.get("kind", ""))),
            )
        self._conn.commit()
        return doc

    def activate(self, doc_id: str) -> KnowledgeDoc:
        doc = self.get(doc_id)
        if doc is None:
            raise KeyError(doc_id)
        if doc.status == "activated":
            return doc
        self._conn.execute(
            "UPDATE docs SET status = 'activated', activated_at = ? WHERE doc_id = ?",
            (datetime.now(UTC).isoformat(), doc_id),
        )
        self._conn.commit()
        return self.get(doc_id)  # type: ignore[return-value]

    # -- reads --------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        status: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        cleaned = query.strip()
        if not cleaned:
            return []
        match = '"' + cleaned.replace('"', '""') + '"'
        sql = (
            "SELECT d.rowid, d.doc_id, d.kind, d.source_ref, d.status, d.title, "
            "bm25(docs_fts) AS score, snippet(docs_fts, 1, '[', ']', '…', 12) AS snip "
            "FROM docs_fts JOIN docs d ON d.rowid = docs_fts.rowid "
            "WHERE docs_fts MATCH ?"
        )
        params: list = [match]
        if status:
            sql += " AND d.status = ?"
            params.append(status)
        if tags:
            placeholders = ",".join("?" * len(tags))
            sql += f" AND d.doc_id IN (SELECT doc_id FROM tags WHERE tag IN ({placeholders}))"
            params.extend(tags)
        sql += " ORDER BY score LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        tag_map = self._tags_for([r[1] for r in rows])
        hits: list[SearchHit] = []
        for row in rows:
            _, doc_id, kind, source_ref, st, title, score, snip = row
            hits.append(
                SearchHit(
                    doc_id=doc_id,
                    kind=kind,
                    source_ref=source_ref,
                    status=st,
                    title=title or "",
                    snippet=snip or "",
                    tags=tag_map.get(doc_id, []),
                    bm25_score=float(score),
                )
            )
        return hits

    def list_docs(self, status: str | None = None, limit: int = 100) -> list[KnowledgeDoc]:
        sql = (
            "SELECT doc_id, kind, source_ref, payload, status, created_at, activated_at "
            "FROM docs"
        )
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        tag_map = self._tags_for([r[0] for r in rows])
        return [self._row_to_doc(r, tag_map.get(r[0], [])) for r in rows]

    def get(self, doc_id: str) -> KnowledgeDoc | None:
        row = self._conn.execute(
            "SELECT doc_id, kind, source_ref, payload, status, created_at, activated_at "
            "FROM docs WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        if row is None:
            return None
        tags = [
            {"tag": tag, "kind": kind}
            for tag, kind in self._conn.execute(
                "SELECT tag, kind FROM tags WHERE doc_id = ? ORDER BY rowid", (doc_id,)
            )
        ]
        return self._row_to_doc(row, tags)

    # -- graph API (S3) -----------------------------------------------------

    def related(self, doc_id: str, limit: int = 5) -> list[dict]:
        """Return docs sharing >=1 tag with *doc_id* ranked by shared count."""

        doc_id = str(doc_id)
        if limit < 1:
            limit = 5

        # Quick existence check — avoids spurious rows when doc_id has no tags.
        if self._conn.execute("SELECT 1 FROM docs WHERE doc_id = ?", (doc_id,)).fetchone() is None:
            return []

        rows = self._conn.execute(
            "SELECT d.doc_id, d.title, COUNT(*) as shared_count, GROUP_CONCAT(t.tag, ',') as shared_tags "
            "FROM docs d "
            "JOIN tags t ON d.doc_id = t.doc_id "
            "WHERE t.tag IN (SELECT tag FROM tags WHERE doc_id = ?) "
            "AND d.doc_id != ? "
            "AND d.status IN ('proposed', 'activated') "
            "GROUP BY d.doc_id "
            "ORDER BY shared_count DESC, d.created_at DESC "
            "LIMIT ?",
            (doc_id, doc_id, limit),
        ).fetchall()

        out: list[dict] = []
        for other_id, title, shared_count, shared_tags_raw in rows:
            tags = [t for t in (shared_tags_raw or "").split(",") if t]
            out.append(
                {
                    "doc_id": other_id,
                    "title": title or "",
                    "shared_tags": sorted(tags),
                    "score": int(shared_count),
                }
            )
        return out

    def graph(self, kind: str | None = None, limit: int = 100) -> dict:
        """Build tag graph from ``tags``.

        Nodes are unique tags with kind and distinct-document count. Edges
        are co-occurrences (pair of tags appearing in the same document),
        weighted by doc count. When *kind* is set, only nodes/edges of that
        kind remain. When *limit* is given only the top-N nodes by count are
        retained (edges among those nodes only).
        """

        # Nodes: one row per (tag, kind) with distinct-doc count.
        if kind is not None:
            node_rows = self._conn.execute(
                "SELECT tag, kind, COUNT(DISTINCT doc_id) as cnt FROM tags "
                "WHERE kind = ? GROUP BY tag, kind ORDER BY cnt DESC",
                (kind,),
            ).fetchall()
        else:
            node_rows = self._conn.execute(
                "SELECT tag, kind, COUNT(DISTINCT doc_id) as cnt FROM tags "
                "GROUP BY tag, kind ORDER BY cnt DESC"
            ).fetchall()

        all_nodes: list[dict] = [
            {"id": tag, "label": tag, "kind": k, "count": int(cnt)} for tag, k, cnt in node_rows
        ]

        if limit is not None and len(all_nodes) > limit:
            kept = set(n["id"] for n in all_nodes[:limit])
            nodes = all_nodes[:limit]
        else:
            kept = set(n["id"] for n in all_nodes) if kind is not None else None
            nodes = all_nodes

        if not nodes:
            return {"nodes": [], "edges": []}

        # Edges via co-occurrence per doc.
        # For each doc, order tags, emit pairs t1<t2 (lexicographic) and count.
        if kind is not None:
            doc_rows = self._conn.execute(
                "SELECT doc_id, tag FROM tags WHERE kind = ? ORDER BY doc_id, tag", (kind,)
            ).fetchall()
        else:
            doc_rows = self._conn.execute("SELECT doc_id, tag FROM tags ORDER BY doc_id, tag").fetchall()

        from collections import defaultdict

        doc_to_tags: dict[str, list[str]] = defaultdict(list)
        for doc_id, tag in doc_rows:
            if kept is None or tag in kept:
                doc_to_tags[doc_id].append(tag)

        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        for tags in doc_to_tags.values():
            uniq = sorted(set(tags))
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    pair_counts[(uniq[i], uniq[j])] += 1

        edges = [
            {"source": s, "target": t, "weight": int(w)}
            for (s, t), w in sorted(pair_counts.items())
        ]

        return {"nodes": nodes, "edges": edges}

    def counts(self) -> dict[str, int]:
        docs = self._conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        proposed = self._conn.execute(
            "SELECT COUNT(*) FROM docs WHERE status = 'proposed'"
        ).fetchone()[0]
        activated = self._conn.execute(
            "SELECT COUNT(*) FROM docs WHERE status = 'activated'"
        ).fetchone()[0]
        tags = self._conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        return {"docs": docs, "proposed": proposed, "activated": activated, "tags": tags}

    # -- sync metadata -------------------------------------------------------

    def set_last_sync(self, ts: str) -> None:
        """Record the most recent sync attempt time (ISO-8601).

        ``set_last_sync_result`` carries the attempt's outcome — a timestamp
        here does not imply success (a failed attempt is still an attempt).
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_sync_at', ?)",
            (ts,),
        )
        self._conn.commit()

    def get_last_sync(self) -> str | None:
        """Return the last sync attempt time (ISO-8601) or None."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'last_sync_at'"
        ).fetchone()
        return row[0] if row else None

    def set_last_sync_result(self, result: str) -> None:
        """Record the outcome of the most recent sync attempt.

        ``result`` is one of "success", "partial", or "failed".
        """
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_sync_result', ?)",
            (result,),
        )
        self._conn.commit()

    def get_last_sync_result(self) -> str | None:
        """Return the outcome of the last sync attempt, or None."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'last_sync_result'"
        ).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self._conn.close()
