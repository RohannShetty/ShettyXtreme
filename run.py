"""ShettyXtreme Terminal entry point.

Loads credentials, starts the server, and opens the browser.
"""
from __future__ import annotations

import sys
import webbrowser

import uvicorn

from shettyxtreme.auth.credential_store import CredentialStore


def main() -> None:
    """Start the ShettyXtreme Terminal."""
    store = CredentialStore.load()

    if store is None or not store.is_complete():
        print("First time setup: open http://127.0.0.1:8000/setup in your browser")
        startup_url = "http://127.0.0.1:8000/setup"
    else:
        if not store.is_trading_valid():
            print("WARNING: Trading token expired — re-authenticate at /settings")
        if not store.is_data_valid():
            print("WARNING: Data token expired — re-authenticate at /settings")
        startup_url = "http://127.0.0.1:8000/"

    webbrowser.open(startup_url)

    uvicorn.run(
        "shettyxtreme.terminal.api.app:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
