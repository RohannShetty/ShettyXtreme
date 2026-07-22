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

    if store is not None:
        if not store.is_trading_valid():
            print("WARNING: Trading token expired — re-authenticate at /settings")
        if not store.is_data_valid():
            print("WARNING: Data token expired — re-authenticate at /settings")

    # Always open the setup wizard; it auto-redirects to the terminal once
    # the connection is complete (see setup.html checkStatus).
    print("Setup wizard: open http://127.0.0.1:8000/static/setup.html in your browser")
    startup_url = "http://127.0.0.1:8000/static/setup.html"

    webbrowser.open(startup_url)

    uvicorn.run(
        "shettyxtreme.terminal.api.app:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
