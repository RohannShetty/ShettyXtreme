"""Auth router for the setup wizard and Fyers OAuth2 callback."""
from __future__ import annotations

import asyncio
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.fyers_oauth import FyersAuthError, FyersOAuthHelper
from shettyxtreme.auth.validator import CredentialValidator
from shettyxtreme.terminal.api.terminal_init import run_terminal_init

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_store: CredentialStore | None = None
_oauth: FyersOAuthHelper | None = None
_validator: CredentialValidator | None = None


def init_auth(
    store: CredentialStore,
    oauth: FyersOAuthHelper,
    validator: CredentialValidator,
) -> None:
    global _store, _oauth, _validator
    _store = store
    _oauth = oauth
    _validator = validator


class CredentialStatusResponse(BaseModel):
    broker: str = "fyers"
    has_api_key: bool = False
    has_token: bool = False
    token_valid: bool = False
    token_expiry: str | None = None
    connected: bool = False
    setup_complete: bool = False
    client_name: str | None = None
    client_id: str | None = None


class AuthStartResponse(BaseModel):
    login_url: str
    state: str


class SaveResult(BaseModel):
    success: bool
    message: str


class CredentialBody(BaseModel):
    app_id: str
    secret_id: str


class ValidationResultResponse(BaseModel):
    valid: bool
    message: str


def _get_store() -> CredentialStore:
    if _store is None:
        return CredentialStore()
    return _store


_bootstrap_lock = asyncio.Lock()


async def _safe_bootstrap() -> None:
    """Trigger the terminal adapter bootstrap after a credential save.

    Failures are logged and swallowed — a bootstrap problem must never
    break the save response the caller is about to return. Serialized so
    concurrent saves cannot double-initialize the adapters.
    """
    try:
        async with _bootstrap_lock:
            await run_terminal_init()
    except Exception:
        logger.error("terminal adapter bootstrap after credential save failed", exc_info=True)


@router.get("/status", response_model=CredentialStatusResponse)
async def get_status() -> CredentialStatusResponse:
    store = _get_store()
    token_valid = store.is_token_valid() if store.access_token else False
    connected = token_valid and bool(store.access_token)
    return CredentialStatusResponse(
        broker=store.broker,
        has_api_key=bool(store.app_id),
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
    store.broker = "fyers"
    store.app_id = body.app_id.strip()
    store.secret_id = body.secret_id.strip()
    store.save()
    await _safe_bootstrap()
    return SaveResult(success=True, message="Credentials saved")


@router.post("/start-auth", response_model=AuthStartResponse)
async def start_auth(request: Request) -> AuthStartResponse:
    store = _get_store()
    if not store.app_id:
        raise HTTPException(
            status_code=400,
            detail="Fyers App ID not configured. Save your app credentials first.",
        )
    if _oauth is None:
        raise HTTPException(status_code=503, detail="Auth helper not initialised")
    redirect_uri = str(request.base_url).rstrip("/") + "/auth/fyers/callback"
    state = secrets.token_urlsafe(16)
    login_url = _oauth.generate_auth_url(
        app_id=store.app_id,
        redirect_uri=redirect_uri,
        state=state,
    )
    return AuthStartResponse(login_url=login_url, state=state)


@router.get("/fyers/callback", response_model=None)
async def fyers_callback(
    request: Request,
    auth_code: str | None = None,
    user_id: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    try:
        if not auth_code:
            logger.debug("Fyers callback missing auth_code (state=%s)", state)
            return RedirectResponse(url="/static/?error=Authentication+failed#/setup")
        store = _get_store()
        if _oauth is None:
            return RedirectResponse(url="/static/?error=Authentication+failed#/setup")
        result = await _oauth.exchange_auth_code(
            app_id=store.app_id,
            secret_id=store.secret_id,
            auth_code=auth_code,
            user_id=user_id,
        )
        store.update_token(
            access_token=result.access_token,
            expiry=result.token_expiry,
            client_id=result.client_id or user_id or store.client_id or "",
        )
        store.save()
        try:
            await run_terminal_init()
        except Exception:
            logger.exception("terminal data pipeline init after login failed")
        return RedirectResponse(url="/static/?connected=true#/setup")

    except FyersAuthError as exc:
        logger.debug("Fyers OAuth exchange failed: %s", exc)
        return RedirectResponse(url="/static/?error=Authentication+failed#/setup")
    except Exception:
        logger.exception("Fyers OAuth callback failed")
        return RedirectResponse(url="/static/?error=Server+error+during+OAuth+callback#/setup")


@router.post("/test", response_model=ValidationResultResponse)
async def test_credentials(body: CredentialBody | None = None) -> ValidationResultResponse:
    store = _get_store()
    assert _validator is not None
    if body:
        app_id = body.app_id.strip()
        secret_id = body.secret_id.strip()
    else:
        app_id = store.app_id
        secret_id = store.secret_id
    result = await _validator.validate_credentials(app_id=app_id, secret_id=secret_id)
    if not result.valid:
        return ValidationResultResponse(valid=False, message=result.message)
    # Live Fyers probe when we already hold an access token.
    if store.access_token:
        probe = await _validator.validate_access_token(
            app_id=store.app_id, access_token=store.access_token
        )
        return ValidationResultResponse(valid=probe.valid, message=probe.message)
    return ValidationResultResponse(
        valid=True,
        message="Credentials valid. Connect Fyers to obtain an access token.",
    )


@router.post("/logout", response_model=SaveResult)
async def logout() -> SaveResult:
    store = _get_store()
    store.access_token = None
    store.token_expiry = None
    store.save()
    return SaveResult(success=True, message="Access tokens cleared")
