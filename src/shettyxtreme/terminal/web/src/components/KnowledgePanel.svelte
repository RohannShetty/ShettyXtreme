<script lang="ts">
  import { onMount } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import type {
    KnowledgeDoc,
    KnowledgeNoteRequest,
    KnowledgeSearchHit,
    KnowledgeSearchResponse,
    KnowledgeStatusResponse,
    KnowledgeSyncResponse,
  } from "../lib/api";

  let query = "";
  let hits: KnowledgeSearchHit[] = [];
  let selected: KnowledgeDoc | null = null;
  let docs: KnowledgeDoc[] = [];
  let status = { docs: 0, proposed: 0, activated: 0, tags: 0 };
  let error = "";
  let searched = false;
  let searching = false;
  let syncing = false;
  let activating = false;
  let syncResult = "";
  let noteTitle = "";
  let noteBody = "";
  let saving = false;
  let debounceTimer: number | undefined;

  function strField(payload: Record<string, unknown>, key: string): string {
    const v = payload[key];
    return typeof v === "string" ? v : "";
  }

  function evidenceItems(payload: Record<string, unknown>): { item: string; source: string }[] {
    const ev = payload["evidence"];
    if (!Array.isArray(ev)) return [];
    const out: { item: string; source: string }[] = [];
    for (const e of ev) {
      if (typeof e !== "object" || e === null) continue;
      const o = e as Record<string, unknown>;
      out.push({
        item: typeof o.item === "string" ? o.item : "",
        source: typeof o.source === "string" ? o.source : "",
      });
    }
    return out;
  }

  function statusClass(statusVal: string): string {
    return statusVal === "activated" ? "ok" : statusVal === "proposed" ? "pending" : "bad";
  }

  function markActivated(docId: string, doc: KnowledgeDoc): void {
    hits = hits.map((h) => (h.doc_id === docId ? { ...h, status: "activated" } : h));
    docs = docs.map((d) => (d.doc_id === docId ? doc : d));
    if (selected && selected.doc_id === docId) selected = doc;
  }

  onMount(() => {
    loadStatus();
    const off = onMessage("knowledge", (data) => {
      const ev = data as { event: string; data: unknown };
      if (ev.event !== "activated") return;
      const doc = ev.data as KnowledgeDoc;
      if (doc && typeof doc.doc_id === "string") markActivated(doc.doc_id, doc);
    });
    return off;
  });

  async function loadStatus(): Promise<void> {
    try {
      status = await get<KnowledgeStatusResponse>("/api/knowledge/status");
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function search(): Promise<void> {
    if (searching) return;
    searching = true;
    searched = true;
    error = "";
    try {
      const resp = await get<KnowledgeSearchResponse>(
        `/api/knowledge/search?q=${encodeURIComponent(query)}&limit=20`,
      );
      hits = resp.hits;
      selected = null;
      if (docs.length === 0 && hits.length > 0) {
        try {
          const list = await get<{ docs: KnowledgeDoc[] }>("/api/knowledge/docs");
          docs = list.docs;
        } catch {
          /* detail falls back to hit fields */
        }
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      hits = [];
    } finally {
      searching = false;
    }
  }

  function onInput(): void {
    if (debounceTimer !== undefined) window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      search();
    }, 300);
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
      if (debounceTimer !== undefined) window.clearTimeout(debounceTimer);
      search();
    }
  }

  async function select(docId: string): Promise<void> {
    const hit = hits.find((h) => h.doc_id === docId);
    if (docs.length === 0) {
      try {
        const list = await get<{ docs: KnowledgeDoc[] }>("/api/knowledge/docs");
        docs = list.docs;
      } catch {
        /* fall back to hit-only detail */
      }
    }
    const doc = docs.find((d) => d.doc_id === docId);
    if (doc) {
      selected = doc;
    } else if (hit) {
      selected = {
        doc_id: hit.doc_id,
        kind: hit.kind,
        source_ref: hit.source_ref,
        payload: { thesis: hit.title },
        status: hit.status,
        created_at: null,
        activated_at: null,
        tags: hit.tags,
      };
    }
  }

  async function activate(): Promise<void> {
    if (!selected || activating || selected.status === "activated") return;
    activating = true;
    error = "";
    try {
      const doc = await post<KnowledgeDoc>(`/api/knowledge/docs/${selected.doc_id}/activate`);
      markActivated(doc.doc_id, doc);
      await loadStatus();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      activating = false;
    }
  }

  async function sync(): Promise<void> {
    if (syncing) return;
    syncing = true;
    syncResult = "";
    error = "";
    try {
      const resp = await post<KnowledgeSyncResponse>("/api/knowledge/sync");
      syncResult = `ingested ${resp.ingested} · undecided ${resp.skipped_undecided} · dupes ${resp.skipped_duplicate}`;
      await loadStatus();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      syncing = false;
    }
  }

  async function saveNote(): Promise<void> {
    if (saving || !noteTitle.trim()) return;
    saving = true;
    error = "";
    try {
      await postBody<KnowledgeDoc>("/api/knowledge/notes", {
        title: noteTitle.trim(),
        body: noteBody,
      } satisfies KnowledgeNoteRequest);
      noteTitle = "";
      noteBody = "";
      await loadStatus();
      await search();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      saving = false;
    }
  }

  function fmtTs(ts: string | null): string {
    if (!ts) return "—";
    return ts.replace("T", " ").replace(/\.\d+Z$/, "Z");
  }
</script>

<section class="panel knowledge">
  <header class="panel-head">
    <h2>Knowledge</h2>
    <div class="head-right">
      <span class="counts mono">{status.docs} docs · {status.proposed} prop · {status.activated} act</span>
      <button class="refresh" on:click={loadStatus} title="Refresh">↻</button>
    </div>
  </header>
  {#if error}
    <p class="error">{error}</p>
  {/if}
  <div class="controls">
    <input class="query mono" type="text" placeholder="Search knowledge…" bind:value={query} on:input={onInput} on:keydown={onKeydown} />
    <button class="run-btn" on:click={search} disabled={searching}>{searching ? "Searching…" : "Search"}</button>
    <button class="run-btn sync" on:click={sync} disabled={syncing}>{syncing ? "Syncing…" : "Sync"}</button>
  </div>
  <div class="note-box">
    <input class="query mono" type="text" placeholder="Note title…" bind:value={noteTitle} />
    <textarea class="note-body mono" rows="2" placeholder="Note body — symbols/regimes auto-tagged…" bind:value={noteBody}></textarea>
    <button class="run-btn" on:click={saveNote} disabled={saving || !noteTitle.trim()}>
      {saving ? "Saving…" : "Save note"}
    </button>
  </div>
  {#if syncResult}
    <p class="sync-result mono">{syncResult}</p>
  {/if}
  <div class="cols">
    <div class="col list-col">
      <ul>
        {#each hits as h (h.doc_id)}
          <button class="row" class:sel={selected && selected.doc_id === h.doc_id} on:click={() => select(h.doc_id)}>
            <span class="row-main">
              <span class="title">{h.title}</span>
              <span class="meta mono"><span class="tag {statusClass(h.status)}">{h.status}</span><span class="src">{h.source_ref}</span></span>
            </span>
            <span class="snippet">{h.snippet}</span>
            <span class="tags">
              {#each h.tags as t (t.tag + t.kind)}
                <span class="tag">{t.tag}</span>
              {/each}
            </span>
          </button>
        {/each}
        {#if !searched && hits.length === 0}
          <li class="empty">Type a query to search knowledge.</li>
        {:else if searched && hits.length === 0}
          <li class="empty">No results.</li>
        {/if}
      </ul>
    </div>
    <div class="col detail-col">
      {#if selected}
        <h3 class="detail-title">{strField(selected.payload, "thesis") || selected.payload["title"]}</h3>
        {#if selected.kind}
          <p class="detail-meta mono">
            <span class="tag {statusClass(selected.status)}">{selected.status}</span>
            <span>{selected.kind}</span>
            <span>{selected.source_ref}</span>
            {#if selected.activated_at}
              <span>activated {fmtTs(selected.activated_at)}</span>
            {/if}
          </p>
        {/if}
        {#if strField(selected.payload, "rationale")}
          <h4>Rationale</h4>
          <p class="detail-text">{strField(selected.payload, "rationale")}</p>
        {/if}
        {#if selected.tags.length > 0}
          <h4>Tags</h4>
          <div class="tags">
            {#each selected.tags as t (t.tag + t.kind)}
              <span class="tag">{t.kind}: {t.tag}</span>
            {/each}
          </div>
        {/if}
        {#if evidenceItems(selected.payload).length > 0}
          <h4>Evidence</h4>
          <ul class="evidence">
            {#each evidenceItems(selected.payload) as e, i (i)}
              <li>
                <span class="ev-item">{e.item}</span>
                {#if e.source}
                  <span class="ev-source mono">{e.source}</span>
                {/if}
              </li>
            {/each}
          </ul>
        {/if}
        <button class="run-btn activate" on:click={activate} disabled={selected.status === "activated" || activating}>
          {selected.status === "activated" ? "Activated" : activating ? "Activating…" : "Activate"}
        </button>
      {:else}
        <p class="empty">Select a result to review it.</p>
      {/if}
    </div>
  </div>
</section>

<style>
  .knowledge { display: flex; flex-direction: column; min-width: 320px; min-height: 0; flex: 1 1 0; border-radius: 6px; background: var(--surface-card); border: 1px solid var(--hairline); }
  .panel-head { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-bottom: 1px solid var(--hairline); }
  .panel-head h2 { margin: 0; font-size: 11px; font-weight: 700; letter-spacing: 0.08em; color: var(--muted); text-transform: uppercase; }
  .head-right { display: flex; align-items: center; gap: 8px; }
  .counts { color: var(--faint); font-size: 9px; }
  .refresh, .run-btn { background: none; border: 1px solid var(--hairline); border-radius: 4px; color: var(--muted); cursor: pointer; padding: 2px 8px; font-size: 13px; }
  .refresh:hover, .run-btn:hover { color: var(--ink); border-color: var(--hairline-strong); }
  .run-btn { border-color: var(--accent); color: var(--accent-active); }
  .run-btn:disabled { opacity: 0.5; cursor: default; }
  .sync { border-color: var(--hairline); color: var(--muted); }
  .activate { align-self: flex-start; margin-top: 8px; }
  .controls { display: flex; gap: 6px; padding: 8px 10px; align-items: center; }
  .note-box { display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; border-bottom: 1px solid var(--hairline); }
  .note-body { background: var(--surface); border: 1px solid var(--hairline); border-radius: 4px; color: var(--body); font-size: 11px; padding: 4px 6px; resize: vertical; }
  .query { flex: 1; background: var(--surface); border: 1px solid var(--hairline); border-radius: 4px; color: var(--body); font-size: 11px; padding: 4px 6px; }
  .query:focus { outline: none; border-color: var(--hairline-strong); }
  .sync-result { margin: 0 10px 6px; font-size: 10px; color: var(--muted); }
  .cols { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(220px, 2fr) minmax(280px, 3fr); overflow: hidden; }
  .col { overflow-y: auto; padding: 8px 10px; }
  .list-col { border-right: 1px solid var(--hairline); }
  ul { list-style: none; margin: 0; padding: 0; }
  .row { display: flex; flex-direction: column; align-items: stretch; gap: 3px; width: 100%; padding: 5px 6px; font-size: 11px; border: none; border-bottom: 1px solid var(--hairline); background: none; color: inherit; text-align: left; cursor: pointer; }
  .row.sel { background: color-mix(in srgb, var(--accent) 10%, transparent); }
  .row-main { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
  .title { color: var(--ink); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .meta { display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; }
  .src { color: var(--faint); font-size: 9px; }
  .snippet { color: var(--body); font-size: 10px; line-height: 1.45; overflow: hidden; display: -webkit-box; line-clamp: 2; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .tag { font-size: 9px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); border: 1px solid var(--hairline-strong); border-radius: 4px; padding: 1px 5px; white-space: nowrap; }
  .tag.ok { color: var(--success); border-color: var(--success); }
  .tag.bad { color: var(--danger); border-color: var(--danger); }
  .tag.pending { color: var(--warning); border-color: var(--warning); }
  .empty { color: var(--faint); font-size: 11px; padding: 4px 0; border-bottom: none; }
  .detail-col h3, .detail-col h4 { margin: 0 0 6px; font-size: 10px; font-weight: 700; letter-spacing: 0.07em; color: var(--faint); text-transform: uppercase; }
  .detail-title { text-transform: none !important; letter-spacing: 0 !important; font-size: 13px !important; font-weight: 600 !important; color: var(--ink) !important; }
  .detail-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 0 0 10px; color: var(--faint); font-size: 10px; }
  .detail-text { color: var(--body); font-size: 11px; line-height: 1.6; margin: 0 0 10px; }
  .evidence { margin: 0 0 10px; }
  .evidence li { display: flex; flex-direction: column; gap: 1px; padding: 3px 0; font-size: 11px; border-bottom: 1px solid var(--hairline); }
  .ev-item { color: var(--body); }
  .ev-source { color: var(--faint); font-size: 9px; }
  .error { color: var(--danger); font-size: 11px; padding: 8px 10px; margin: 0; }
</style>
