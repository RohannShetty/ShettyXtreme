"""Auth router for onboarding wizard and Dhan OAuth callback."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import DhanOAuthHelper
from shettyxtreme.auth.validator import CredentialValidator

logger = logging.getLogger(__name__)

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


class CredentialStatusResponse(BaseModel):
    has_api_key: bool = False
    has_token: bool = False
    token_valid: bool = False
    token_expiry: str | None = None
    connected: bool = False
    setup_complete: bool = False
    client_name: str | None = None
    client_id: str | None = None


class ConsentStartResponse(BaseModel):
    consent_app_id: str
    login_url: str


class SaveResult(BaseModel):
    success: bool
    message: str


class CredentialBody(BaseModel):
    api_key: str
    api_secret: str


def _split_combined_key(api_key: str) -> tuple[str, str]:
    """Split the combined `client_id:::api_key` format used by the setup UI.

    Returns (client_id, api_key). If no `:::` separator is present the whole
    value is treated as the api_key with an empty client_id.
    """
    if ":::" in api_key:
        client_id, _, key = api_key.partition(":::")
        return client_id.strip(), key.strip()
    return "", api_key.strip()


class ValidationResultResponse(BaseModel):
    valid: bool
    message: str


def _get_store() -> CredentialStore:
    if _store is None:
        return CredentialStore()
    return _store


@router.get("/status", response_model=CredentialStatusResponse)
async def get_status() -> CredentialStatusResponse:
    store = _get_store()
    token_valid = store.is_token_valid() if store.access_token else False
    connected = token_valid and bool(store.access_token)
    return CredentialStatusResponse(
        has_api_key=bool(store.api_key),
        has_token=bool(store.access_token),
        token_valid=token_valid,
        token_expiry=store.token_expiry,
        connected=connected,
        setup_complete=connected,
        client_name=store.client_name,
        client_id=store.client_id,
    )


@router.post("/credentials", response_model=SaveResult)
async def save_credentials(body: CredentialBody) -> SaveResult:
    store = _get_store()
    client_id, api_key = _split_combined_key(body.api_key)
    store.api_key = api_key
    store.api_secret = body.api_secret
    if client_id:
        store.client_id = client_id
    store.save()
    return SaveResult(success=True, message="Credentials saved")


@router.post("/start-consent", response_model=ConsentStartResponse)
async def start_consent() -> ConsentStartResponse:
    store = _get_store()
    assert _oauth is not None
    consent_app_id = await _oauth.generate_consent(
        api_key=store.api_key,
        api_secret=store.api_secret,
        client_id=store.client_id or "",
    )
    if not consent_app_id:
        raise HTTPException(
            status_code=502,
            detail="Failed to generate consent. Check your API credentials and ensure the OAuth redirect URL is set correctly in the Dhan Developer Portal.",
        )
    login_url = _oauth.get_login_url(consent_app_id)
    return ConsentStartResponse(
        consent_app_id=consent_app_id,
        login_url=login_url,
    )


@router.get("/dhan/callback", response_model=None)
async def dhan_callback(tokenId: str) -> RedirectResponse:
    try:
        store = _get_store()
        result = await _oauth.consume_consent(
            api_key=store.api_key,
            api_secret=store.api_secret,
            token_id=tokenId,
        )
        if result:
            store.update_token(
                access_token=result.access_token,
                expiry=result.expiry_time,
                client_id=result.client_id,
            )
            store.client_name = result.client_name
            store.save()
            return RedirectResponse(url="/static/setup.html?connected=true")
        return RedirectResponse(url="/static/setup.html?error=consent_failed")

    except Exception:
        logger.exception("OAuth callback failed")
        return RedirectResponse(url="/static/setup.html?error=server_error")


@router.post("/test", response_model=ValidationResultResponse)
async def test_credentials(body: CredentialBody | None = None) -> ValidationResultResponse:
    store = _get_store()
    assert _validator is not None
    if body:
        client_id, api_key = _split_combined_key(body.api_key)
        api_secret = body.api_secret
    else:
        client_id = store.client_id or ""
        api_key = store.api_key
        api_secret = store.api_secret
    result = await _validator.validate_credentials(
        api_key=api_key,
        api_secret=api_secret,
        client_id=client_id,
    )
    return ValidationResultResponse(valid=result.valid, message=result.message)


@router.post("/logout", response_model=SaveResult)
async def logout() -> SaveResult:
    store = _get_store()
    store.access_token = None
    store.save()
    return SaveResult(success=True, message="Access tokens cleared")
