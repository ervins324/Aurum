"""Pydantic schemas for the integrations endpoints.

Credentials are write-only: the read schema never returns the raw token/key.
Instead it returns:
  - is_configured: whether credentials are stored
  - token_preview / key_preview: a masked glimpse (first 3 + last 3 chars)
"""
from __future__ import annotations

from datetime import date as date_
from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationRead(BaseModel):
    """Safe read-only view — no plaintext credentials exposed."""

    provider: str
    is_configured: bool
    is_syncing: bool = False
    # Live status message updated throughout the background sync run.
    # None when idle; cleared once the task finishes.
    sync_status: str | None = None
    # Masked preview shown in the UI so the user knows something is stored,
    # e.g. "uUm…xQ9" for a Monobank token.
    token_preview: str | None = None
    key_preview: str | None = None
    account_id: int | None
    last_synced_at: datetime | None
    last_sync_result: IntegrationSyncResult | None = None


class MonobankIntegrationSet(BaseModel):
    """Payload for saving/updating Monobank credentials."""

    token: str = Field(min_length=10, description="Monobank personal token from api.monobank.ua")
    account_id: int = Field(description="Aurum account ID where synced transactions land")



class IntegrationSyncResult(BaseModel):
    """Summary returned after a sync run."""

    provider: str
    synced_count: int
    skipped_count: int
    # Human-readable error message if the sync partially or fully failed.
    error: str | None = None


class MonobankSyncRequest(BaseModel):
    """Optional period override for a Monobank sync run."""

    sync_from: date_ | None = Field(default=None, description="Earliest date to fetch (YYYY-MM-DD)")
    sync_to: date_ | None = Field(default=None, description="Latest date to fetch (YYYY-MM-DD)")

