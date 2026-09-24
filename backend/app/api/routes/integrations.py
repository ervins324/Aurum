"""Integrations API routes.

GET  /integrations            → list both providers (masked read)
PUT  /integrations/monobank   → save/update Monobank token + account
PUT  /integrations/bybit      → save/update Bybit key + secret + account
DELETE /integrations/{provider} → remove credentials
POST /integrations/{provider}/sync → trigger a sync run
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.integration import (
    BybitIntegrationSet,
    IntegrationRead,
    IntegrationSyncResult,
    MonobankIntegrationSet,
    MonobankSyncRequest,
)
from app.services.integration_service import (
    delete_integration,
    list_integrations,
    sync_bybit,
    sync_monobank,
    upsert_bybit,
    upsert_monobank,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])

_VALID_PROVIDERS = {"monobank", "bybit"}


@router.get("", response_model=list[IntegrationRead])
async def read_integrations(session: AsyncSession = Depends(get_session)) -> list[IntegrationRead]:
    """Return the status (masked, no plaintext credentials) for all providers."""
    return await list_integrations(session)


@router.put("/monobank", response_model=IntegrationRead)
async def set_monobank(
    payload: MonobankIntegrationSet,
    session: AsyncSession = Depends(get_session),
) -> IntegrationRead:
    """Save or replace Monobank token and linked account."""
    return await upsert_monobank(session, payload)


@router.put("/bybit", response_model=IntegrationRead)
async def set_bybit(
    payload: BybitIntegrationSet,
    session: AsyncSession = Depends(get_session),
) -> IntegrationRead:
    """Save or replace Bybit API key + secret and linked account."""
    return await upsert_bybit(session, payload)


@router.delete("/{provider}", status_code=204)
async def remove_integration(
    provider: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete stored credentials for the given provider."""
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    await delete_integration(session, provider)


@router.post("/{provider}/sync", response_model=IntegrationSyncResult)
async def trigger_sync(
    provider: str,
    payload: MonobankSyncRequest = Body(default=MonobankSyncRequest()),
    session: AsyncSession = Depends(get_session),
) -> IntegrationSyncResult:
    """Trigger a sync for the given provider.

    For Monobank, an optional JSON body with sync_from / sync_to dates
    narrows the sync window.  Without them, defaults to _MONO_EPOCH → today.
    Syncing a narrow period (e.g. last 7 days) skips the 61-second waits
    and finishes in seconds.
    """
    if provider == "monobank":
        return await sync_monobank(session, sync_from=payload.sync_from, sync_to=payload.sync_to)
    if provider == "bybit":
        return await sync_bybit(session)
    raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

