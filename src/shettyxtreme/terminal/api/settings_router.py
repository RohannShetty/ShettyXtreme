"""Settings router for credential management UI."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import DhanOAuthHelper
from shettyxtreme.auth.validator import CredentialValidator

router = APIRouter(prefix="/api/settings", tags=["settings"])

_store: CredentialStore | None = None
_oauth: DhanOAuthHelper | None = None
_validator: CredentialValidator | None = None


def init_settings(
    store: CredentialStore,
    oauth: DhanOAuthHelper,
    validator: CredentialValidator,
) -> None:
    global _store, _oauth, _validator
    _store = store
    _oauth = oauth
    _validator = validator


class PostbackUrlResponse(BaseModel):
    url: str
    instructions: str


class CredentialsResponse(BaseModel):
    api_key_masked: str
    client_id: str | None = None
    token_valid: bool = False
    token_expiry: str | None = None


class ConsentResponse(BaseModel):
    consent_app_id: str
    login_url: str


class ValidationResultResponse(BaseModel):
    valid: bool
    message: str


def _get_store() -> CredentialStore:
    if _store is None:
        return CredentialStore()
    return _store


@router.get("")
async def get_settings() -> dict:
    return {"page": "settings", "message": "Settings page - serve via /static/settings.html"}


@router.get("/credentials", response_model=CredentialsResponse)
async def get_credentials() -> CredentialsResponse:
    store = _get_store()
    masked = store.get_masked()
    return CredentialsResponse(
        api_key_masked=masked.get("api_key", ""),
        client_id=store.client_id,
        token_valid=store.is_token_valid() if store.access_token else False,
        token_expiry=store.token_expiry,
    )


@router.post("/reauth", response_model=ConsentResponse)
async def reauth() -> ConsentResponse:
    store = _get_store()
    assert _oauth is not None
    consent_app_id = await _oauth.generate_consent(
        api_key=store.api_key,
        api_secret=store.api_secret,
        client_id=store.client_id or "",
    )
    login_url = _oauth.get_login_url(consent_app_id or "")
    return ConsentResponse(
        consent_app_id=consent_app_id or "",
        login_url=login_url,
    )


@router.post("/test", response_model=ValidationResultResponse)
async def test_credentials() -> ValidationResultResponse:
    store = _get_store()
    assert _validator is not None
    result = await _validator.validate_credentials(
        api_key=store.api_key,
        api_secret=store.api_secret,
        client_id=store.client_id or "",
    )
    return ValidationResultResponse(valid=result.valid, message=result.message)


@router.post("/postback-url", response_model=PostbackUrlResponse)
async def get_postback_url() -> PostbackUrlResponse:
    return PostbackUrlResponse(
        url="http://localhost:8000/api/postback/dhan",
        instructions="Register this URL in Dhan Developer Portal -> Your API App -> Postback URL",
    )
