"""ShettyXtreme Terminal entry point.

Loads credentials, sets the execution mode (OBSERVER default; LIVE requires
explicit per-session confirmation per D10), starts the server, opens the
browser.
"""
from __future__ import annotations

import argparse
import sys
import webbrowser

import uvicorn

from shettyxtreme.auth.credential_store import CredentialStore


def main() -> None:
    """Start the ShettyXtreme Terminal."""
    parser = argparse.ArgumentParser(description="ShettyXtreme Terminal")
    parser.add_argument(
        "--mode",
        choices=["OBSERVER", "PAPER", "LIVE"],
        default="OBSERVER",
        help="Execution mode (default: OBSERVER; LIVE requires confirmation)",
    )
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    parser.add_argument("--port", type=int, default=8000, help="Uvicorn port (default: 8000)")
    args = parser.parse_args()

    if args.mode == "LIVE":
        answer = input("LIVE mode places real orders. Type 'LIVE' to confirm: ").strip().upper()
        if answer != "LIVE":
            print("Aborted: LIVE mode not confirmed.")
            sys.exit(1)

    from shettyxtreme.terminal.api import execution_router
    execution_router._current_mode = args.mode
    execution_router._save_mode(args.mode)

    store = CredentialStore.load()

    if store is not None:
        if not store.is_token_valid():
            print("WARNING: Token expired — re-authenticate at /settings")

    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{args.port}/")

    uvicorn.run(
        "shettyxtreme.terminal.api.app:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
