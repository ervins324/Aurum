"""Integration service — manages credential storage and sync logic for
external bank providers (Monobank).

Monobank sync strategy:
  - Uses GET /personal/client-info to verify the token is valid.
  - Fetches statements in rolling 30-day chunks from the *oldest possible
    Monobank date* (2017-11-01, when Monobank launched) all the way to today,
    respecting the 60-second inter-request rate limit by sleeping between chunks.
  - Upserts transactions using external_id = "mono_{item_id}"; already-seen
    records are silently skipped.
"""

import asyncio
import logging
from datetime import date as date_
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt, encrypt, mask
from app.models.enums import TransactionType
from app.models.integration import Integration
from app.models.transaction import Transaction
from app.schemas.integration import (
    IntegrationRead,
    IntegrationSyncResult,
    MonobankIntegrationSet,
)

logger = logging.getLogger("aurum.integration")

# Monobank API constants
_MONO_BASE = "https://api.monobank.ua"
# Monobank statement history start: January 1, 2025 as requested
_MONO_EPOCH = date_(2025, 1, 1)
# Monobank's maximum statement window per request (30 days in seconds).
_MONO_CHUNK_SECS = 2_592_000  # 30 days exactly

# Active background sync tasks & last results by provider
_ACTIVE_SYNC_TASKS: dict[str, asyncio.Task] = {}
_LAST_SYNC_RESULTS: dict[str, IntegrationSyncResult] = {}
# Live one-line progress message per provider, set during background sync.
# Cleared when the task finishes so the UI reverts to showing the final result.
_SYNC_STATUS: dict[str, str] = {}


def _set_sync_status(provider: str, message: str) -> None:
    """Update the live progress message visible on the next GET /integrations poll."""
    _SYNC_STATUS[provider] = message


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_read(integration: Integration | None, provider: str) -> IntegrationRead:
    """Build the safe (masked) read schema from an ORM row (or None = unconfigured)."""
    task = _ACTIVE_SYNC_TASKS.get(provider)
    is_syncing = task is not None and not task.done()
    last_res = _LAST_SYNC_RESULTS.get(provider)
    # Only surface live status while sync is actually running
    sync_status = _SYNC_STATUS.get(provider) if is_syncing else None

    if integration is None:
        return IntegrationRead(
            provider=provider,
            is_configured=False,
            is_syncing=is_syncing,
            sync_status=sync_status,
            token_preview=None,
            key_preview=None,
            account_id=None,
            last_synced_at=None,
            last_sync_result=last_res,
        )
    # Determine masked previews from encrypted blobs
    token_preview: str | None = None
    key_preview: str | None = None
    if integration.token_enc:
        try:
            token_preview = mask(decrypt(integration.token_enc))
        except Exception:
            token_preview = "***"
    if integration.api_key_enc:
        try:
            key_preview = mask(decrypt(integration.api_key_enc))
        except Exception:
            key_preview = "***"

    return IntegrationRead(
        provider=provider,
        is_configured=True,
        is_syncing=is_syncing,
        sync_status=sync_status,
        token_preview=token_preview,
        key_preview=key_preview,
        account_id=integration.account_id,
        last_synced_at=integration.last_synced_at,
        last_sync_result=last_res,
    )


async def _get_integration(session: AsyncSession, provider: str) -> Integration | None:
    result = await session.execute(
        select(Integration).where(Integration.provider == provider)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def list_integrations(session: AsyncSession) -> list[IntegrationRead]:
    """Return read schemas for providers, whether configured or not."""
    mono = await _get_integration(session, "monobank")
    return [_to_read(mono, "monobank")]


async def upsert_monobank(
    session: AsyncSession, payload: MonobankIntegrationSet
) -> IntegrationRead:
    """Save (or replace) Monobank credentials."""
    integration = await _get_integration(session, "monobank")
    if integration is None:
        integration = Integration(provider="monobank")
        session.add(integration)

    integration.token_enc = encrypt(payload.token)
    integration.account_id = payload.account_id
    await session.commit()
    await session.refresh(integration)
    return _to_read(integration, "monobank")


async def delete_integration(session: AsyncSession, provider: str) -> None:
    """Remove stored credentials for a provider."""
    integration = await _get_integration(session, provider)
    if integration is None:
        return
    await session.delete(integration)
    await session.commit()


# ---------------------------------------------------------------------------
# Background sync orchestration
# ---------------------------------------------------------------------------


async def start_background_sync(
    provider: str,
    sync_from: date_ | None = None,
    sync_to: date_ | None = None,
) -> IntegrationSyncResult:
    """Start an integration sync as a detached background task.

    If a sync is already running for the provider, returns a result indicating
    that sync is in progress. Otherwise, launches an asyncio task that operates
    on its own database session and returns an immediate response.
    """
    task = _ACTIVE_SYNC_TASKS.get(provider)
    if task is not None and not task.done():
        logger.info(
            "[Sync] Sync already running in background for '%s'; ignoring duplicate trigger",
            provider,
        )
        return IntegrationSyncResult(
            provider=provider,
            synced_count=0,
            skipped_count=0,
            error="Sync already in progress",
        )

    from app.db.session import AsyncSessionLocal

    async def _worker() -> None:
        logger.info(
            "[Background Sync] Detached background task started for '%s'", provider
        )
        async with AsyncSessionLocal() as session:
            try:
                if provider == "monobank":
                    result = await sync_monobank(
                        session, sync_from=sync_from, sync_to=sync_to
                    )
                else:
                    result = IntegrationSyncResult(
                        provider=provider,
                        synced_count=0,
                        skipped_count=0,
                        error="Unknown provider",
                    )
                _LAST_SYNC_RESULTS[provider] = result
                logger.info(
                    "[Background Sync] Finished for '%s': %d synced, %d skipped, error=%s",
                    provider,
                    result.synced_count,
                    result.skipped_count,
                    result.error,
                )
            except Exception as exc:
                logger.error(
                    "[Background Sync] Uncaught error during '%s' sync: %s",
                    provider,
                    exc,
                    exc_info=True,
                )
                _LAST_SYNC_RESULTS[provider] = IntegrationSyncResult(
                    provider=provider,
                    synced_count=0,
                    skipped_count=0,
                    error=str(exc),
                )
            finally:
                _ACTIVE_SYNC_TASKS.pop(provider, None)
                # Clear live status so the UI reverts to showing the final result
                _SYNC_STATUS.pop(provider, None)

    task = asyncio.create_task(_worker())
    _ACTIVE_SYNC_TASKS[provider] = task
    logger.info("[Sync] Dispatched background task for '%s'", provider)
    return IntegrationSyncResult(
        provider=provider, synced_count=0, skipped_count=0, error=None
    )


# ---------------------------------------------------------------------------
# Monobank sync
# ---------------------------------------------------------------------------


async def sync_monobank(
    session: AsyncSession,
    sync_from: date_ | None = None,
    sync_to: date_ | None = None,
) -> IntegrationSyncResult:
    """Fetch Monobank history for the given period, chunk by chunk.

    Parameters:
      sync_from — earliest date to fetch (defaults to _MONO_EPOCH).
      sync_to   — latest date to fetch (defaults to today).

    Rate limit: Monobank allows 1 statement request per 60 seconds per token.
    We sleep 61 seconds between chunks. Each chunk is committed immediately so
    progress is preserved even if stopped mid-sync.
    """
    from app.services.mcc_service import (
        resolve_category_id_by_mcc,
        resolve_fallback_other_category,
    )

    integration = await _get_integration(session, "monobank")
    if integration is None or not integration.token_enc:
        logger.warning("[Monobank Sync] Attempted sync but Monobank is not configured")
        return IntegrationSyncResult(
            provider="monobank", synced_count=0, skipped_count=0, error="Not configured"
        )
    if integration.account_id is None:
        logger.warning("[Monobank Sync] Attempted sync but no Aurum account is linked")
        return IntegrationSyncResult(
            provider="monobank",
            synced_count=0,
            skipped_count=0,
            error="No account linked",
        )

    try:
        token = decrypt(integration.token_enc)
    except Exception as exc:
        logger.error("[Monobank Sync] Failed to decrypt token: %s", exc)
        return IntegrationSyncResult(
            provider="monobank", synced_count=0, skipped_count=0, error=str(exc)
        )

    headers = {"X-Token": token}
    account_id = integration.account_id

    # Resolve sync period
    effective_from = sync_from or _MONO_EPOCH
    effective_to = sync_to or date_.today()

    logger.info(
        "[Monobank Sync] Starting sync for account_id=%s. Period: %s to %s",
        account_id,
        effective_from,
        effective_to,
    )
    _set_sync_status("monobank", f"Connecting… ({effective_from} → {effective_to})")

    mono_account_ids: list[str] = ["0"]

    synced = 0
    skipped = 0
    end_ts = int(
        datetime(
            effective_to.year,
            effective_to.month,
            effective_to.day,
            23,
            59,
            59,
            tzinfo=timezone.utc,
        ).timestamp()
    )
    start_ts = int(
        datetime(
            effective_from.year,
            effective_from.month,
            effective_from.day,
            tzinfo=timezone.utc,
        ).timestamp()
    )

    for mono_acc_id in mono_account_ids:
        chunk_end_ts = end_ts
        first_request = True
        chunk_idx = 0

        while chunk_end_ts > start_ts:
            chunk_start_ts = max(chunk_end_ts - _MONO_CHUNK_SECS, start_ts)
            chunk_idx += 1

            chunk_start_str = datetime.fromtimestamp(
                chunk_start_ts, tz=timezone.utc
            ).strftime("%Y-%m-%d")
            chunk_end_str = datetime.fromtimestamp(
                chunk_end_ts, tz=timezone.utc
            ).strftime("%Y-%m-%d")

            # Mono rate limit: 1 req / 60 s — sleep between all but first call
            if not first_request:
                logger.info(
                    "[Monobank Sync] Rate limit: sleeping 61s before fetching next chunk…"
                )
                # Count down 61 seconds so the UI shows the remaining wait time
                for remaining in range(61, 0, -1):
                    _set_sync_status(
                        "monobank",
                        f"Rate limit — waiting {remaining}s before chunk #{chunk_idx} ({chunk_start_str} → {chunk_end_str})…",
                    )
                    await asyncio.sleep(1)
            first_request = False

            logger.info(
                "[Monobank Sync] Chunk #%d: requesting statement [%s -> %s] for card '%s'",
                chunk_idx,
                chunk_start_str,
                chunk_end_str,
                mono_acc_id,
            )
            _set_sync_status(
                "monobank",
                f"Fetching chunk #{chunk_idx}: {chunk_start_str} → {chunk_end_str}…",
            )

            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        f"{_MONO_BASE}/personal/statement/{mono_acc_id}/{chunk_start_ts}/{chunk_end_ts}",
                        headers=headers,
                    )
                    if resp.status_code == 429:
                        logger.warning(
                            "[Monobank Sync] 429 Too Many Requests received from Monobank — waiting 120s"
                        )
                        for remaining in range(120, 0, -1):
                            _set_sync_status(
                                "monobank", f"Rate limit (429) — waiting {remaining}s…"
                            )
                            await asyncio.sleep(1)
                        continue
                    resp.raise_for_status()
                    items = resp.json()
            except Exception as exc:
                logger.error(
                    "[Monobank Sync] Statement fetch failed for card '%s' [%s -> %s]: %s",
                    mono_acc_id,
                    chunk_start_str,
                    chunk_end_str,
                    exc,
                )
                _set_sync_status(
                    "monobank", f"Error fetching chunk #{chunk_idx}: {exc}"
                )
                break

            logger.info(
                "[Monobank Sync] API returned %d items for chunk #%d",
                len(items),
                chunk_idx,
            )
            _set_sync_status(
                "monobank",
                f"Processing chunk #{chunk_idx}: {len(items)} transactions ({synced} saved so far)…",
            )

            # Batch deduplication: one query per chunk instead of one per transaction.
            ext_ids_in_chunk = [f"mono_{item['id']}" for item in items]
            if ext_ids_in_chunk:
                existing_result = await session.execute(
                    select(Transaction.external_id).where(
                        Transaction.external_id.in_(ext_ids_in_chunk)
                    )
                )
                already_synced: set[str] = {row[0] for row in existing_result.all()}
            else:
                already_synced = set()

            chunk_synced = 0
            chunk_skipped = 0

            for item in items:
                ext_id = f"mono_{item['id']}"
                if ext_id in already_synced:
                    chunk_skipped += 1
                    skipped += 1
                    continue

                raw_amount = Decimal(str(item["amount"])) / Decimal("100")
                if raw_amount < 0:
                    tx_type = TransactionType.EXPENSE
                    amount = abs(raw_amount)
                else:
                    tx_type = TransactionType.INCOME
                    amount = raw_amount

                # Parse precise timestamp (UTC) and derive date from it
                tx_timestamp = datetime.fromtimestamp(item["time"], tz=timezone.utc)
                tx_date = tx_timestamp.date()
                description = item.get("description") or "Monobank transaction"

                # Auto-categorise by MCC code; fall back to "Other" category if none matched
                mcc = item.get("mcc")
                category_id = await resolve_category_id_by_mcc(session, mcc, tx_type)
                if category_id is None:
                    category_id = await resolve_fallback_other_category(
                        session, tx_type
                    )

                tx = Transaction(
                    account_id=account_id,
                    type=tx_type,
                    amount=amount,
                    description=description[:255],
                    date=tx_date,
                    transaction_time=tx_timestamp,
                    external_id=ext_id,
                    category_id=category_id,
                    notes=f"MCC: {item.get('mcc', '')}" if item.get("mcc") else None,
                )
                session.add(tx)
                chunk_synced += 1
                synced += 1

            # Commit after each chunk so progress is immediately saved in the DB
            _set_sync_status(
                "monobank",
                f"Saving chunk #{chunk_idx}: {chunk_synced} new, {chunk_skipped} duplicates (total: {synced} saved)…",
            )
            await session.commit()
            logger.info(
                "[Monobank Sync] Chunk #%d committed: %d new added, %d skipped duplicates. Total progress: %d synced, %d skipped",
                chunk_idx,
                chunk_synced,
                chunk_skipped,
                synced,
                skipped,
            )

            # Move window back
            chunk_end_ts = chunk_start_ts - 1

    _set_sync_status("monobank", f"Finalising… {synced} transactions saved.")
    integration.last_synced_at = datetime.now(tz=timezone.utc)
    await session.commit()
    logger.info(
        "[Monobank Sync] Completed successfully for %s -> %s: %d total synced, %d total skipped",
        effective_from,
        effective_to,
        synced,
        skipped,
    )
    return IntegrationSyncResult(
        provider="monobank", synced_count=synced, skipped_count=skipped
    )

