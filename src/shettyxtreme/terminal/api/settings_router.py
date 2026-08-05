"""Settings router.

Fyers does not use postback webhooks (fills arrive over the order WebSocket),
so the Dhan postback-URL helper is gone. The credential management surface
lives in auth_router (`/auth/*`). This router intentionally carries no
endpoints — retained so the composition root keeps a stable include.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/settings", tags=["settings"])
