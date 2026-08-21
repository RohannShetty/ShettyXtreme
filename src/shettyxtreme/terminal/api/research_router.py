"""Research router — run briefers, tools, decisions, scoring (Phase 3B + 3C).

The orchestrator is created lazily on first run; without DEEPSEEK_API_KEY
the run endpoint returns 503 with an explicit message. DB failures on
read paths degrade to empty/404 payloads — never 500. Broadcasts go out
on WS topic `research` via the broadcast_fn wired in lifespan.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
)
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, OutcomeTracker
from shettyxtreme.research.briefs import ResearchBrief
from shettyxtreme.research.lenses import list_lenses
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import DeepSeekProvider
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.store import (
    AlreadyDecidedError,
    BriefNotDecidedError,
    ResearchStore,
)
from shettyxtreme.research.tools import list_tools
from shettyxtreme.terminal.api.models import (
    LensInfoResponse,
    LensListResponse,
    ResearchBriefListResponse,
    ResearchBriefResponse,
    ResearchDecisionResponse,
    ResearchOutcomeRequest,
    ResearchOutcomeResponse,
    ResearchRunItem,
    ResearchRunRequest,
    ResearchRunResponse,
    ResearchSchedulerResponse,
    ResearchScoringItem,
    ResearchScoringResponse,
    ResearchToolResponse,
    ResearchToolsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])

RESEARCH_DB_PATH = "data/research.db"
LEARNING_DB_PATH = "data/learning.db"
_ORCHESTRATOR: ResearchOrchestrator | None = None
_broadcast_fn: Callable[[dict], None] | None = None
_SCHEDULER: ResearchScheduler | None = None


def init_research(
    broadcast_fn: Callable[[dict], None] | None = None,
    scheduler: ResearchScheduler | None = None,
) -> None:
    """Wire WS broadcast + the scheduled-run handle (lifespan calls this)."""
    global _broadcast_fn, _SCHEDULER
    _broadcast_fn = broadcast_fn
    _SCHEDULER = scheduler


def _broadcast(event: dict) -> None:
    if _broadcast_fn is None:
        return
    try:
        _broadcast_fn(event)
    except Exception:
        logger.exception("research broadcast failed")


def _brief_response(brief: ResearchBrief) -> ResearchBriefResponse:
    return ResearchBriefResponse(**brief.model_dump(), expired=brief.is_expired())


def _on_brief(brief: ResearchBrief) -> None:
    _broadcast({"event": "new_brief", "data": _brief_response(brief).model_dump()})


def build_orchestrator() -> ResearchOrchestrator | None:
    """Build a key-gated orchestrator wired for broadcasts (router + scheduler)."""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return None
    return ResearchOrchestrator(
        provider=DeepSeekProvider(),
        store=ResearchStore(RESEARCH_DB_PATH),
        on_brief=_on_brief,
    )


def _get_orchestrator() -> ResearchOrchestrator | None:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is not None:
        return _ORCHESTRATOR
    _ORCHESTRATOR = build_orchestrator()
    return _ORCHESTRATOR


def _open_store() -> ResearchStore:
    """Open the research store; propagate exceptions to callers."""
    return ResearchStore(RESEARCH_DB_PATH)


@router.get("/lenses", response_model=LensListResponse)
async def lenses() -> LensListResponse:
    """Available briefer lenses."""
    return LensListResponse(
        lenses=[
            LensInfoResponse(name=l.name, description=l.description)
            for l in list_lenses()
        ]
    )


@router.get("/tools", response_model=ResearchToolsResponse)
async def tools() -> ResearchToolsResponse:
    """Read-only tool definitions (single source for REST + function calling)."""
    return ResearchToolsResponse(
        tools=[
            ResearchToolResponse(
                name=t.name, description=t.description, params_schema=t.params_schema
            )
            for t in list_tools()
        ]
    )


@router.get("/scheduler", response_model=ResearchSchedulerResponse)
async def scheduler_status() -> ResearchSchedulerResponse:
    """Scheduler status; enabled only when the lifespan started it."""
    if _SCHEDULER is None:
        return ResearchSchedulerResponse()
    return ResearchSchedulerResponse(
        enabled=_SCHEDULER.enabled,
        interval_minutes=_SCHEDULER.interval_minutes,
        lenses=_SCHEDULER.lenses,
        tools=_SCHEDULER.tools,
        next_run_at=_SCHEDULER.next_run_at,
        last_run_at=_SCHEDULER.last_run_at,
        last_result=_SCHEDULER.last_result,
    )


@router.post("/run", response_model=ResearchRunResponse)
async def run(req: ResearchRunRequest) -> ResearchRunResponse:
    """Run one research pass across the requested (or all) lenses."""
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY is not set — set it to enable research runs",
        )
    if req.lenses:
        valid = {l.name for l in list_lenses()}
        unknown = [n for n in req.lenses if n not in valid]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown lenses: {unknown}; valid: {sorted(valid)}",
            )
    if req.tools:
        valid_tools = {t.name for t in list_tools()}
        unknown_tools = [n for n in req.tools if n not in valid_tools]
        if unknown_tools:
            raise HTTPException(
                status_code=400,
                detail=f"unknown tools: {unknown_tools}; valid: {sorted(valid_tools)}",
            )
    results = await orch.run(lenses=req.lenses, sources=req.context, tools=req.tools)
    items = [
        ResearchRunItem(
            lens=r.lens,
            brief=_brief_response(r.brief) if r.brief else None,
            error=r.error,
        )
        for r in results
    ]
    return ResearchRunResponse(results=items)


@router.get("/briefs", response_model=ResearchBriefListResponse)
async def list_briefs(
    status: str | None = None, lens: str | None = None
) -> ResearchBriefListResponse:
    """List briefs, newest first, optionally filtered."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        return ResearchBriefListResponse()
    try:
        return ResearchBriefListResponse(
            briefs=[_brief_response(b) for b in store.list(status=status, lens=lens)]
        )
    except Exception as exc:
        logger.warning("Research list failed: %s", exc)
        return ResearchBriefListResponse()
    finally:
        store.close()


@router.get("/briefs/{brief_id}", response_model=ResearchBriefResponse)
async def get_brief(brief_id: str) -> ResearchBriefResponse:
    """Fetch one brief by id."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        brief = store.get(brief_id)
    finally:
        store.close()
    if brief is None:
        raise HTTPException(status_code=404, detail="brief not found")
    return _brief_response(brief)


@router.post("/briefs/{brief_id}/approve", response_model=ResearchDecisionResponse)
async def approve(brief_id: str, request: Request) -> ResearchDecisionResponse:
    """Approve a proposed brief (immutable decision)."""
    return _decide(request, brief_id, "approved")


@router.post("/briefs/{brief_id}/reject", response_model=ResearchDecisionResponse)
async def reject(brief_id: str, request: Request) -> ResearchDecisionResponse:
    """Reject a proposed brief (immutable decision)."""
    return _decide(request, brief_id, "rejected")


_KNOWN_REGIMES = {"trending_up", "trending_down", "range_bound", "volatile", "transition"}


def _normalize_regime(value: object) -> str | None:
    """Lowercase enum value for regime strings; None for anything unknown."""
    if value is None:
        return None
    text = str(value).strip().lower()
    return text if text in _KNOWN_REGIMES else None


def _current_regime(request: Request) -> str | None:
    """Best-effort current regime from the intelligence projection."""
    proj = getattr(request.app.state, "intelligence_projection", None)
    if proj is None:
        return None
    if not proj.has_data():
        return None
    try:
        regime = proj.get_regime() or {}
    except Exception:
        return None
    value = regime.get("regime")
    return _normalize_regime(value)


def _record_brief_decision(brief: ResearchBrief) -> None:
    """Mirror an approved brief into the learning store (best-effort).

    Learning is a side effect of research: a failure here is logged and
    never changes the research response. Decisions key on ``research:<id>``
    so the outcome endpoint can link WIN/LOSS back without a lookup table.
    """
    if brief.status != "approved":
        return
    direction = {1: SignalDirection.UP, -1: SignalDirection.DOWN, 0: SignalDirection.NEUTRAL}.get(
        brief.direction, SignalDirection.NEUTRAL
    )
    try:
        decided_at = (
            datetime.fromisoformat(brief.decided_at)
            if brief.decided_at
            else datetime.now(UTC)
        )
    except ValueError:
        decided_at = datetime.now(UTC)
    signal = Signal(
        direction=direction,
        conviction=brief.confidence,
        voters=[],
        timestamp=decided_at,
    )
    try:
        tracker = OutcomeTracker(LEARNING_DB_PATH)
        try:
            tracker.record_decision_with_id(
                f"research:{brief.brief_id}",
                signal,
                {
                    "kind": "research",
                    "brief_id": brief.brief_id,
                    "lens": brief.lens,
                    "status": brief.status,
                    "direction": brief.direction,
                    "regime_at_decision": brief.regime_at_decision,
                },
            )
        finally:
            tracker.close()
    except Exception as exc:
        logger.warning("learning decision recording failed for %s: %s", brief.brief_id, exc)


def _record_brief_outcome(brief: ResearchBrief) -> None:
    """Mirror a realized research outcome into the learning store (best-effort)."""
    if not brief.outcome or brief.outcome not in ("WIN", "LOSS"):
        return
    try:
        tracker = OutcomeTracker(LEARNING_DB_PATH)
        try:
            tracker.record_outcome_idempotent(
                f"research:{brief.brief_id}", OutcomeLabel(brief.outcome.lower())
            )
        finally:
            tracker.close()
    except Exception as exc:
        logger.warning("learning outcome recording failed for %s: %s", brief.brief_id, exc)


# ── S1: Export helpers ───────────────────────────────────────────────────────


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def _brief_to_markdown(brief: ResearchBrief) -> str:
    """Render a brief to the canonical export Markdown (spec S1).

    Pure function — easy to unit test without an HTTP layer.
    """
    confidence_pct = f"{brief.confidence * 100:.0f}"
    direction = str(brief.direction)
    outcome = brief.outcome if brief.outcome else "Not decided"
    decided_at = brief.decided_at if brief.decided_at else "N/A"
    regime = brief.regime_at_decision if brief.regime_at_decision else "N/A"
    lines: list[str] = []
    lines.append(f"# Research Brief: {brief.brief_id}")
    lines.append("")
    lines.append(f"**Lens:** {brief.lens}  ")
    lines.append(f"**Direction:** {direction}  ")
    lines.append(f"**Confidence:** {confidence_pct}%  ")
    lines.append(f"**Status:** {brief.status}  ")
    lines.append(f"**Generated:** {brief.as_of}  ")
    lines.append(f"**Valid Until:** {brief.validity_window_minutes} minutes")
    lines.append("")
    lines.append("## Thesis")
    lines.append(brief.thesis or "")
    lines.append("")
    lines.append("## Rationale")
    lines.append(brief.rationale or "")
    lines.append("")
    lines.append("## Evidence")
    lines.append("| Item | Source |")
    lines.append("|------|--------|")
    for ev in brief.evidence or []:
        if isinstance(ev, dict):
            item = str(ev.get("item", ""))
            source = str(ev.get("source", ""))
        else:
            item = str(ev)
            source = ""
        lines.append(f"| {_escape_md(item)} | {_escape_md(source)} |")
    lines.append("")
    lines.append("## Risks")
    if brief.risks:
        for r in brief.risks:
            lines.append(f"- {r}")
    else:
        lines.append("_No risks listed._")
    lines.append("")
    lines.append("## Metadata")
    lines.append(f"- **Outcome:** {outcome}")
    lines.append(f"- **Decided At:** {decided_at}")
    lines.append(f"- **Regime at Decision:** {regime}")
    lines.append("")
    return "\n".join(lines)


def _markdown_to_pdf_bytes(md_text: str) -> bytes:
    """Convert markdown to PDF bytes.

    Strategy: markdown → HTML (optional) → weasyprint → PDF.  If either
    optional dep is missing, try fpdf2.  If neither is installed, return a
    minimal hand-rolled PDF (valid header, contains the md text as stream).
    Any failure raises RuntimeError so the route can map to 500.
    """
    # Attempt weasyprint path (markdown + weasyprint)
    try:
        import markdown as md_lib  # type: ignore[import-untyped]

        html_body = md_lib.markdown(md_text, extensions=["tables", "fenced_code"])
        try:
            from weasyprint import HTML  # type: ignore[import-untyped]

            styled_html = (
                "<html><head><meta charset='utf-8'><style>"
                "body{font-family: ui-monospace, monospace; font-size: 11px; color: #111; line-height:1.5; margin: 24px;}"
                "h1{font-size:18px; margin-bottom:8px;} h2{font-size:13px; margin-top:16px; color:#222;}"
                "table{border-collapse:collapse; width:100%; margin:8px 0;}"
                "th,td{border:1px solid #ccc; padding:4px 6px; text-align:left; font-size:10px;}"
                "code,pre{font-family: ui-monospace, monospace; background:#f5f5f5; padding:2px 4px;}"
                "</style></head><body>" + html_body + "</body></html>"
            )
            pdf_bytes = HTML(string=styled_html).write_pdf()
            if pdf_bytes and pdf_bytes[:5] == b"%PDF-":
                return pdf_bytes
        except ImportError:
            pass
        except Exception as exc:  # weasyprint can fail on missing system libs
            logger.warning("weasyprint PDF generation failed: %s", exc)
            # fall through to fpdf2
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("markdown conversion failed: %s", exc)

    # Attempt fpdf2 path
    try:
        from fpdf import FPDF  # type: ignore[import-untyped]

        pdf = FPDF(format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)
        for line in md_text.splitlines():
            # FPDF doesn't support markdown; dump as plain text
            safe = line.encode("latin-1", errors="replace").decode("latin-1")
            pdf.multi_cell(0, 5, safe)
        out = pdf.output()
        if isinstance(out, (bytes, bytearray)):
            data = bytes(out)
        else:
            data = out.encode("latin-1")  # fpdf2 with dest='S' returns str in some versions
        if data[:5] == b"%PDF-":
            return data
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("fpdf2 PDF generation failed: %s", exc)
        raise RuntimeError(f"PDF generation failed: {exc}") from exc

    # Minimal fallback — valid PDF header guaranteed for offline/CI without deps
    def _pdf_escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops: list[str] = ["BT", "/F1 8 Tf", "72 750 Td"]
    for idx, raw in enumerate(md_text.splitlines()[:180]):
        safe = _pdf_escape(raw[:120])
        if idx == 0:
            ops.append(f"({safe}) Tj")
        else:
            ops.append("0 -12 Td")
            ops.append(f"({safe}) Tj")
        if idx * 12 > 700:
            break
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1", errors="replace")
    # Minimal PDF structure
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    # Objects
    objs: list[bytes] = []
    objs.append(b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n")
    objs.append(b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n")
    objs.append(b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>/Contents 4 0 R>>endobj\n")
    objs.append(b"4 0 obj<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream endobj\n")
    # xref
    offset = len(header)
    offsets = []
    for o in objs:
        offsets.append(offset)
        offset += len(o)
    xref_pos = offset
    xref = b"xref\n0 5\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    trailer = b"trailer<</Size 5/Root 1 0 R>>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return header + b"".join(objs) + xref + trailer


def _decide(request: Request, brief_id: str, decision: str) -> ResearchDecisionResponse:
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        try:
            brief = store.decide(
                brief_id,
                decision,
                regime=_normalize_regime(_current_regime(request)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="brief not found") from exc
        except AlreadyDecidedError as exc:
            raise HTTPException(status_code=409, detail="brief already decided") from exc
    finally:
        store.close()
    _broadcast(
        {"event": "decision", "data": {"brief_id": brief.brief_id, "status": brief.status}}
    )
    _record_brief_decision(brief)
    return ResearchDecisionResponse(brief_id=brief.brief_id, status=brief.status)


@router.post("/briefs/{brief_id}/outcome", response_model=ResearchOutcomeResponse)
async def set_outcome(
    brief_id: str, body: ResearchOutcomeRequest
) -> ResearchOutcomeResponse:
    """Record a realized outcome (WIN|LOSS) for a decided brief."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        try:
            brief = store.set_outcome(brief_id, body.outcome)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="brief not found") from exc
        except BriefNotDecidedError as exc:
            raise HTTPException(
                status_code=409,
                detail="outcome can only be recorded for a decided brief",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        store.close()
    _record_brief_outcome(brief)
    return ResearchOutcomeResponse(
        brief_id=brief.brief_id, outcome=brief.outcome or ""
    )


@router.get("/scoring", response_model=ResearchScoringResponse)
async def scoring() -> ResearchScoringResponse:
    """Per-lens brief scoring aggregates; empty DB -> []."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        return ResearchScoringResponse()
    try:
        return ResearchScoringResponse(
            lenses=[ResearchScoringItem(**row) for row in store.scoring()]
        )
    except Exception as exc:
        logger.warning("Research scoring failed: %s", exc)
        return ResearchScoringResponse()
    finally:
        store.close()


@router.get("/briefs/{brief_id}/export")
async def export_brief(brief_id: str, format: str = Query("md")) -> Response:
    """Export a brief as Markdown or PDF (spec S1).

    Query `format` must be ``md`` or ``pdf``.  Missing brief -> 404,
    unsupported format -> 400, PDF failure -> 500.
    """
    if format not in ("md", "pdf"):
        raise HTTPException(status_code=400, detail="unsupported format: use md or pdf")
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        brief = store.get(brief_id)
    finally:
        try:
            store.close()
        except Exception:
            pass
    if brief is None:
        raise HTTPException(status_code=404, detail="brief not found")
    md_text = _brief_to_markdown(brief)
    if format == "md":
        return Response(
            content=md_text,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="brief-{brief_id}.md"'},
        )
    try:
        pdf_bytes = _markdown_to_pdf_bytes(md_text)
    except RuntimeError as exc:
        logger.exception("PDF generation failed for %s", brief_id)
        raise HTTPException(status_code=500, detail="PDF generation failed") from exc
    except Exception as exc:
        logger.exception("PDF generation failed for %s: %s", brief_id, exc)
        raise HTTPException(status_code=500, detail="PDF generation failed") from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="brief-{brief_id}.pdf"'},
    )
