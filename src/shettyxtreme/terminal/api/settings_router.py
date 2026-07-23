"""Settings router for credential management UI."""
from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import DhanOAuthHelper
from shettyxtreme.auth.validator import CredentialValidator

router = APIRouter(prefix="/settings", tags=["settings"])

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


# ── Pydantic models ────────────────────────────────────────────────────────
class PostbackUrlResponse(BaseModel):
    url: str
    instructions: str


class CredentialsResponse(BaseModel):
    trading_api_key_masked: str
    trading_client_id: str
    trading_valid: bool
    trading_expiry: str | None = None
    data_api_key_masked: str
    data_client_id: str
    data_valid: bool
    data_expiry: str | None = None


class ConsentResponse(BaseModel):
    consent_app_id: str
    login_url: str


class ValidationResultResponse(BaseModel):
    valid: bool
    message: str


# ── Helpers ─────────────────────────────────────────────────────────────────
def _get_store() -> CredentialStore:
    if _store is None:
        return CredentialStore()
    return _store


# ── Endpoints ───────────────────────────────────────────────────────────────
@router.get("")
async def get_settings() -> dict:
    return {"page": "settings", "message": "Settings page - serve via /static/settings.html"}


@router.get("/credentials", response_model=CredentialsResponse)
async def get_credentials() -> CredentialsResponse:
    store = _get_store()
    trading_valid = store.is_trading_valid() if store.trading_access_token else False
    data_valid = store.is_data_valid() if store.data_access_token else False
    return CredentialsResponse(
        trading_api_key_masked=store.get_masked().get("trading_api_key", ""),
        trading_client_id=store.trading_client_id or "",
        trading_valid=trading_valid,
        trading_expiry=store.trading_token_expiry,
        data_api_key_masked=store.get_masked().get("data_api_key", ""),
        data_client_id=store.data_client_id or "",
        data_valid=data_valid,
        data_expiry=store.data_token_expiry,
    )


@router.post("/reauth/trading", response_model=ConsentResponse)
async def reauth_trading() -> ConsentResponse:
    store = _get_store()
    assert _oauth is not None
    consent_app_id = await _oauth.generate_consent(
        api_key=store.trading_api_key,
        api_secret=store.trading_api_secret,
        client_id=store.trading_client_id or "",
        state="trading",
    )
    login_url = _oauth.get_login_url(consent_app_id or "")
    return ConsentResponse(
        consent_app_id=consent_app_id or "",
        login_url=login_url,
    )


@router.post("/reauth/data", response_model=ConsentResponse)
async def reauth_data() -> ConsentResponse:
    store = _get_store()
    assert _oauth is not None
    consent_app_id = await _oauth.generate_consent(
        api_key=store.data_api_key,
        api_secret=store.data_api_secret,
        client_id=store.data_client_id or "",
        state="data",
    )
    login_url = _oauth.get_login_url(consent_app_id or "")
    return ConsentResponse(
        consent_app_id=consent_app_id or "",
        login_url=login_url,
    )


@router.post("/test/trading", response_model=ValidationResultResponse)
async def test_trading() -> ValidationResultResponse:
    store = _get_store()
    assert _validator is not None
    result = await _validator.validate_trading(
        api_key=store.trading_api_key,
        api_secret=store.trading_api_secret,
        client_id=store.trading_client_id or "",
    )
    return ValidationResultResponse(valid=result.valid, message=result.message)


@router.post("/test/data", response_model=ValidationResultResponse)
async def test_data() -> ValidationResultResponse:
    store = _get_store()
    assert _validator is not None
    result = await _validator.validate_data(
        api_key=store.data_api_key,
        api_secret=store.data_api_secret,
        client_id=store.data_client_id or "",
    )
    return ValidationResultResponse(valid=result.valid, message=result.message)


@router.post("/postback-url", response_model=PostbackUrlResponse)
async def get_postback_url() -> PostbackUrlResponse:
    return PostbackUrlResponse(
        url="http://localhost:8000/api/postback/dhan",
        instructions="Register this URL in Dhan Developer Portal -> Your API App -> Postback URL",
    )
