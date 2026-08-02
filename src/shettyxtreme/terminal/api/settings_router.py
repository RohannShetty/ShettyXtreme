"""Settings router — postback URL helper only.

The credential management surface lives in auth_router (`/auth/*`);
this router keeps the one genuinely useful settings endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PostbackUrlResponse(BaseModel):
    url: str
    instructions: str


@router.post("/postback-url", response_model=PostbackUrlResponse)
async def get_postback_url() -> PostbackUrlResponse:
    return PostbackUrlResponse(
        url="http://localhost:8000/api/postback/dhan",
        instructions="Register this URL in Dhan Developer Portal -> Your API App -> Postback URL",
    )
