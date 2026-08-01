"""Manual DeepSeek research smoke run — requires DEEPSEEK_API_KEY.

Usage:
    $env:DEEPSEEK_API_KEY = "sk-..."
    & .\.venv\Scripts\python.exe scripts\research_smoke.py

Exit codes: 0 = all lenses produced briefs; 1 = some/all failed; 2 = no key.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import DeepSeekProvider
from shettyxtreme.research.store import ResearchStore


SOURCES = {
    "regime": "NIFTY 24,700; regime=TRENDING_UP; adx=28; D=0.6 P=0.55 G=trending",
    "scanners": "breakout: NIFTY above 20-day high; gap_up: BANKNIFTY +0.8%",
    "options_intel": "IV rank 62 (elevated); PCR 0.9; OI buildup at 24,800 CE",
}


async def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not set — refusing to run")
        return 2
    store = ResearchStore("data/research.db")
    orch = ResearchOrchestrator(provider=DeepSeekProvider(), store=store)
    results = await orch.run(sources=SOURCES)
    failures = 0
    for r in results:
        if r.error:
            failures += 1
            print(f"[{r.lens}] ERROR: {r.error}")
        else:
            print(
                f"[{r.lens}] direction={r.brief.direction:+d} "
                f"confidence={r.brief.confidence:.2f} — {r.brief.thesis}"
            )
    store.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
