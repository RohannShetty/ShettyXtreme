"""ShettyXtreme terminal — FastAPI backend + web frontend."""
from shettyxtreme.terminal.api.app import ShettyXtremeAPI, ws_manager

__all__ = ["ShettyXtremeAPI", "ws_manager"]
