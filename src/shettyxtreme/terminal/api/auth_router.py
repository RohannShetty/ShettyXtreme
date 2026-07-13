"""Auth router for onboarding wizard and Dhan OAuth callback."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import DhanOAuthHelper
from shettyxtreme.auth.validator import CredentialValidator

router = APIRouter(prefix="/auth", tags=["auth"])

_store: CredentialStore | None = None
_oauth: DhanOAuthHelper | None = None
_validator: CredentialValidator | None = None


def init_auth(
    store: CredentialStore,
    oauth: DhanOAuthHelper,
    validator: CredentialValidator,
) -> None:
    global _store, _oauth, _validator
    _store = store
    _oauth = oauth
    _validator = validator


# ── Pydantic models ────────────────────────────────────────────────────────
class CredentialStatusResponse(BaseModel):
    trading_has_api_key: bool = False
    trading_has_token: bool = False
    trading_valid: bool = False
    trading_expiry: str | None = None
    data_has_api_key: bool = False
    data_has_token: bool = False
    data_valid: bool = False
    data_expiry: str | None = None


class ConsentStartResponse(BaseModel):
    consent_app_id: str
    login_url: str


class SaveResult(BaseModel):
    success: bool
    message: str


class CredentialBody(BaseModel):
    api_key: str
    api_secret: str


class ClientIdBody(BaseModel):
    client_id: str


class ValidationResultResponse(BaseModel):
    valid: bool
    message: str


# ── Helpers ─────────────────────────────────────────────────────────────────
def _get_store() -> CredentialStore:
    if _store is None:
        return CredentialStore()
    return _store


# ── Endpoints ───────────────────────────────────────────────────────────────
@router.get("/status", response_model=CredentialStatusResponse)
async def get_status() -> CredentialStatusResponse:
    store = _get_store()
    trading_valid = store.is_trading_valid() if store.trading_access_token else False
    data_valid = store.is_data_valid() if store.data_access_token else False
    return CredentialStatusResponse(
        trading_has_api_key=bool(store.trading_api_key),
        trading_has_token=bool(store.trading_access_token),
        trading_valid=trading_valid,
        trading_expiry=store.trading_token_expiry,
        data_has_api_key=bool(store.data_api_key),
        data_has_token=bool(store.data_access_token),
        data_valid=data_valid,
        data_expiry=store.data_token_expiry,
    )


@router.post("/credentials/trading", response_model=SaveResult)
async def save_trading_credentials(body: CredentialBody) -> SaveResult:
    store = _get_store()
    store.trading_api_key = body.api_key
    store.trading_api_secret = body.api_secret
    store.save()
    return SaveResult(success=True, message="Trading credentials saved")


@router.post("/credentials/data", response_model=SaveResult)
async def save_data_credentials(body: CredentialBody) -> SaveResult:
    store = _get_store()
    store.data_api_key = body.api_key
    store.data_api_secret = body.api_secret
    store.save()
    return SaveResult(success=True, message="Data credentials saved")


@router.post("/start-consent/trading", response_model=ConsentStartResponse)
async def start_consent_trading(body: ClientIdBody) -> ConsentStartResponse:
    store = _get_store()
    assert _oauth is not None
    consent_app_id = await _oauth.generate_consent(
        api_key=store.trading_api_key,
        api_secret=store.trading_api_secret,
        client_id=body.client_id,
    )
    login_url = _oauth.get_login_url(consent_app_id or "")
    return ConsentStartResponse(
        consent_app_id=consent_app_id or "",
        login_url=login_url,
    )


@router.post("/start-consent/data", response_model=ConsentStartResponse)
async def start_consent_data(body: ClientIdBody) -> ConsentStartResponse:
    store = _get_store()
    assert _oauth is not None
    consent_app_id = await _oauth.generate_consent(
        api_key=store.data_api_key,
        api_secret=store.data_api_secret,
        client_id=body.client_id,
    )
    login_url = _oauth.get_login_url(consent_app_id or "")
    return ConsentStartResponse(
        consent_app_id=consent_app_id or "",
        login_url=login_url,
    )


@router.get("/dhan/callback")
async def dhan_callback(tokenId: str) -> RedirectResponse:
    store = _get_store()
    assert _oauth is not None
    result = await _oauth.consume_consent(
        api_key=store.trading_api_key,
        api_secret=store.trading_api_secret,
        token_id=tokenId,
    )
    if result:
        store.update_trading_token(
            access_token=result.access_token,
            expiry=result.expiry_time,
            client_id=result.client_id,
        )
        store.save()
    return RedirectResponse(url="/")


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


@router.post("/logout", response_model=SaveResult)
async def logout() -> SaveResult:
    store = _get_store()
    store.trading_access_token = None
    store.data_access_token = None
    store.save()
    return SaveResult(success=True, message="Access tokens cleared")
