"""Integrations API routes.

GET  /integrations            → list providers (masked read)
PUT  /integrations/monobank   → save/update Monobank token + account
DELETE /integrations/{provider} → remove credentials
POST /integrations/{provider}/sync → trigger a sync run
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.integration import (
    IntegrationRead,
    IntegrationSyncResult,
    MonobankIntegrationSet,
    MonobankSyncRequest,
)
from app.services.integration_service import (
    _get_integration,
    delete_integration,
    list_integrations,
    start_background_sync,
    sync_monobank,
    upsert_monobank,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])

_VALID_PROVIDERS = {"monobank"}


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
    background: bool = Query(default=True, description="Run sync as detached background task"),
    session: AsyncSession = Depends(get_session),
) -> IntegrationSyncResult:
    """Trigger a sync for the given provider.

    By default, runs as a detached background task on the backend, allowing
    the client to navigate between tabs or close the browser without interrupting
    the sync process. Pass ?background=false to await sync completion synchronously.

    For Monobank, an optional JSON body with sync_from / sync_to dates
    narrows the sync window. Without them, defaults to _MONO_EPOCH → today.
    """
    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    # Check configuration on request session for instant validation feedback
    integration = await _get_integration(session, provider)
    if integration is None or not integration.token_enc:
        return IntegrationSyncResult(provider=provider, synced_count=0, skipped_count=0, error="Not configured")
    if integration.account_id is None:
        return IntegrationSyncResult(provider=provider, synced_count=0, skipped_count=0, error="No account linked")

    if background:
        return await start_background_sync(provider, sync_from=payload.sync_from, sync_to=payload.sync_to)

    return await sync_monobank(session, sync_from=payload.sync_from, sync_to=payload.sync_to)

