"""Integration service — manages credential storage and sync logic for
external bank/exchange providers (Monobank, Bybit Card).

Monobank sync strategy:
  - Uses GET /personal/client-info to verify the token is valid.
  - Fetches statements in rolling 30-day chunks from the *oldest possible
    Monobank date* (2017-11-01, when Monobank launched) all the way to today,
    respecting the 60-second inter-request rate limit by sleeping between chunks.
  - Upserts transactions using external_id = "mono_{item_id}"; already-seen
    records are silently skipped.

Bybit sync strategy:
  - Calls /v5/card/transaction/query-asset-records with cursor-based pagination.
  - For UAH-denominated transactions: uses transactionAmount directly.
  - For non-UAH transactions: converts basicAmount (USDT) to UAH using the NBU
    USD/UAH rate for the transaction date (USDT ≈ USD for this purpose, as per
    the integration spec).
  - Skips failed/declined transactions (status == "2").
"""
import asyncio
from datetime import date as date_
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt, encrypt, mask
from app.models.enums import TransactionType
from app.models.integration import Integration
from app.models.transaction import Transaction
from app.schemas.integration import (
    BybitIntegrationSet,
    IntegrationRead,
    IntegrationSyncResult,
    MonobankIntegrationSet,
)
from app.services.nbu_rate_service import get_usd_uah_rate

logger = logging.getLogger("aurum.integration")

# Monobank API constants
_MONO_BASE = "https://api.monobank.ua"
# Monobank statement history start: January 1, 2025 as requested
_MONO_EPOCH = date_(2025, 1, 1)
# Monobank's maximum statement window per request (30 days in seconds).
_MONO_CHUNK_SECS = 2_592_000  # 30 days exactly

# Bybit API constants
_BYBIT_BASE = "https://api.bybit.com"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_read(integration: Integration | None, provider: str) -> IntegrationRead:
    """Build the safe (masked) read schema from an ORM row (or None = unconfigured)."""
    if integration is None:
        return IntegrationRead(
            provider=provider,
            is_configured=False,
            token_preview=None,
            key_preview=None,
            account_id=None,
            last_synced_at=None,
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
        token_preview=token_preview,
        key_preview=key_preview,
        account_id=integration.account_id,
        last_synced_at=integration.last_synced_at,
    )


async def _get_integration(session: AsyncSession, provider: str) -> Integration | None:
    result = await session.execute(select(Integration).where(Integration.provider == provider))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def list_integrations(session: AsyncSession) -> list[IntegrationRead]:
    """Return read schemas for both providers, whether configured or not."""
    mono = await _get_integration(session, "monobank")
    bybit = await _get_integration(session, "bybit")
    return [_to_read(mono, "monobank"), _to_read(bybit, "bybit")]


async def upsert_monobank(session: AsyncSession, payload: MonobankIntegrationSet) -> IntegrationRead:
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


async def upsert_bybit(session: AsyncSession, payload: BybitIntegrationSet) -> IntegrationRead:
    """Save (or replace) Bybit credentials."""
    integration = await _get_integration(session, "bybit")
    if integration is None:
        integration = Integration(provider="bybit")
        session.add(integration)

    integration.api_key_enc = encrypt(payload.api_key)
    integration.api_secret_enc = encrypt(payload.api_secret)
    integration.account_id = payload.account_id
    await session.commit()
    await session.refresh(integration)
    return _to_read(integration, "bybit")


async def delete_integration(session: AsyncSession, provider: str) -> None:
    """Remove stored credentials for a provider."""
    integration = await _get_integration(session, provider)
    if integration is None:
        return
    await session.delete(integration)
    await session.commit()


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
    We sleep 61 seconds between chunks.  A full history import spanning years
    takes many minutes — this is expected and clearly documented.
    """
    from app.services.mcc_service import resolve_category_id_by_mcc

    integration = await _get_integration(session, "monobank")
    if integration is None or not integration.token_enc:
        return IntegrationSyncResult(provider="monobank", synced_count=0, skipped_count=0, error="Not configured")
    if integration.account_id is None:
        return IntegrationSyncResult(provider="monobank", synced_count=0, skipped_count=0, error="No account linked")

    try:
        token = decrypt(integration.token_enc)
    except Exception as exc:
        return IntegrationSyncResult(provider="monobank", synced_count=0, skipped_count=0, error=str(exc))

    headers = {"X-Token": token}
    account_id = integration.account_id

    # Resolve sync period
    effective_from = sync_from or _MONO_EPOCH
    effective_to = sync_to or date_.today()

    # In Monobank Open API, account "0" is the client's primary active card.
    # Calling /personal/statement/0/... directly avoids burning the 1 req/60s quota
    # on /personal/client-info, preventing an immediate HTTP 429 rate limit error.
    mono_account_ids: list[str] = ["0"]

    synced = 0
    skipped = 0
    end_ts = int(datetime(effective_to.year, effective_to.month, effective_to.day, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    start_ts = int(datetime(effective_from.year, effective_from.month, effective_from.day, tzinfo=timezone.utc).timestamp())

    for mono_acc_id in mono_account_ids:
        # Walk backwards from effective_to to effective_from in 30-day chunks
        chunk_end_ts = end_ts
        first_request = True

        while chunk_end_ts > start_ts:
            chunk_start_ts = max(chunk_end_ts - _MONO_CHUNK_SECS, start_ts)

            # Mono rate limit: 1 req / 60 s — sleep between all but first call
            if not first_request:
                logger.info("Monobank rate-limit sleep 61s…")
                await asyncio.sleep(61)
            first_request = False

            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        f"{_MONO_BASE}/personal/statement/{mono_acc_id}/{chunk_start_ts}/{chunk_end_ts}",
                        headers=headers,
                    )
                    if resp.status_code == 429:
                        # Unexpected 429 — wait longer
                        logger.warning("Monobank 429 — sleeping extra 120s")
                        await asyncio.sleep(120)
                        continue
                    resp.raise_for_status()
                    items = resp.json()
            except Exception as exc:
                logger.error("Monobank statement fetch failed for %s: %s", mono_acc_id, exc)
                break

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

            for item in items:
                ext_id = f"mono_{item['id']}"
                if ext_id in already_synced:
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

                # Auto-categorise by MCC code
                mcc = item.get("mcc")
                category_id = await resolve_category_id_by_mcc(session, mcc, tx_type)

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
                synced += 1

            # Move window back
            chunk_end_ts = chunk_start_ts - 1

        # Flush after each Monobank account to avoid giant pending sets
        await session.flush()

    integration.last_synced_at = datetime.now(tz=timezone.utc)
    await session.commit()
    logger.info("Monobank sync complete: %d synced, %d skipped", synced, skipped)
    return IntegrationSyncResult(provider="monobank", synced_count=synced, skipped_count=skipped)


# ---------------------------------------------------------------------------
# Bybit sync
# ---------------------------------------------------------------------------


def _bybit_sign_post(api_key: str, api_secret: str, recv_window: int, timestamp: int, body_str: str) -> str:
    """HMAC-SHA256 signature for Bybit v5 POST requests."""
    param_str = f"{timestamp}{api_key}{recv_window}{body_str}"
    return hmac.new(
        key=api_secret.encode("utf-8"),
        msg=param_str.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


async def sync_bybit(session: AsyncSession) -> IntegrationSyncResult:
    """Fetch all Bybit Card transaction history via cursor-based pagination.

    Currency handling:
    - transactionCurrency == "UAH": use transactionAmount directly.
    - Other currencies: basicAmount (USDT) × NBU USD/UAH rate for that date.
      (USDT tracks USD 1:1 for this conversion purpose, per spec.)
    """
    integration = await _get_integration(session, "bybit")
    if integration is None or not integration.api_key_enc or not integration.api_secret_enc:
        return IntegrationSyncResult(provider="bybit", synced_count=0, skipped_count=0, error="Not configured")
    if integration.account_id is None:
        return IntegrationSyncResult(provider="bybit", synced_count=0, skipped_count=0, error="No account linked")

    try:
        api_key = decrypt(integration.api_key_enc)
        api_secret = decrypt(integration.api_secret_enc)
    except Exception as exc:
        return IntegrationSyncResult(provider="bybit", synced_count=0, skipped_count=0, error=str(exc))

    account_id = integration.account_id
    recv_window = 5000
    # Bybit Card API requires a 'type' parameter when querying transaction history
    # without a specific txnId or orderNo.
    # SIDE_QUERY_AUTH_ALL retrieves all authorization transactions.
    # SIDE_QUERY_FINANCIAL_ALL retrieves all clearing/settlement transactions.
    query_types = ["SIDE_QUERY_AUTH_ALL", "SIDE_QUERY_FINANCIAL_ALL"]

    for q_type in query_types:
        cursor: str | None = None
        while True:
            ts = int(time.time() * 1000)
            body_dict: dict = {"type": q_type}
            if cursor:
                body_dict["cursor"] = cursor
            body_str = json.dumps(body_dict, separators=(",", ":"))

            signature = _bybit_sign_post(api_key, api_secret, recv_window, ts, body_str)
            headers = {
                "X-BAPI-API-KEY": api_key,
                "X-BAPI-TIMESTAMP": str(ts),
                "X-BAPI-SIGN": signature,
                "X-BAPI-RECV-WINDOW": str(recv_window),
                "X-BAPI-SIGN-TYPE": "2",
                "Content-Type": "application/json",
                "User-Agent": "Aurum/1.1",
            }

            data = None
            last_http_status = None
            last_http_text = ""

            # Try primary URL, then regional fallback (api.bytick.com)
            for base_url in (_BYBIT_BASE, "https://api.bytick.com"):
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.post(
                            f"{base_url}/v5/card/transaction/query-asset-records",
                            headers=headers,
                            content=body_str,
                        )
                        last_http_status = resp.status_code
                        last_http_text = resp.text
                        if resp.status_code == 200 and resp.text:
                            try:
                                data = resp.json()
                                break
                            except Exception:
                                pass
                except Exception as net_err:
                    logger.warning("Bybit endpoint %s failed: %s", base_url, net_err)
                    continue

            if data is None:
                if last_http_status is not None:
                    errors.append(f"HTTP {last_http_status}: {last_http_text[:120] if last_http_text else 'Empty response'}")
                else:
                    errors.append("Connection to Bybit failed (all endpoints unreachable)")
                break

            ret_code = data.get("retCode", -1)
            # Retryable rate-limit codes
            if ret_code in (10006, 10014) or last_http_status == 429:
                logger.warning("Bybit rate limit hit — sleeping 5s")
                await asyncio.sleep(5)
                continue
            if ret_code != 0:
                errors.append(f"Bybit API error retCode={ret_code}: {data.get('retMsg')}")
                break

            records = (data.get("result") or {}).get("list", [])
            next_cursor = (data.get("result") or {}).get("nextPageCursor", "")

            for item in records:
                item_id = item.get("id") or item.get("txnId") or item.get("orderNo")
                if not item_id:
                    continue

                # Skip failed/declined transactions
                status = str(item.get("status") or item.get("tradeStatus") or "")
                if status in ("2", "FAILED", "DECLINED"):
                    skipped += 1
                    continue

                ext_id = f"bybit_{item_id}"
                existing = await session.execute(
                    select(Transaction).where(Transaction.external_id == ext_id)
                )
                if existing.scalar_one_or_none() is not None:
                    skipped += 1
                    continue

                # Determine transaction type
                is_refund = (
                    item.get("is_refund", False)
                    or str(item.get("side", "")) in ("4", "5", "8", "10", "11")
                    or "REFUND" in str(item.get("type", "")).upper()
                )
                tx_type = TransactionType.INCOME if is_refund else TransactionType.EXPENSE

                # Parse transaction timestamp (milliseconds)
                tx_time_raw = (
                    item.get("transactionTime")
                    or item.get("transTime")
                    or item.get("createTime")
                    or item.get("time")
                    or item.get("createdTime")
                    or "0"
                )
                try:
                    tx_time_ms = int(tx_time_raw)
                    tx_timestamp = datetime.fromtimestamp(tx_time_ms / 1000, tz=timezone.utc)
                    tx_date = tx_timestamp.date()
                except (ValueError, OSError):
                    tx_timestamp = None
                    tx_date = date_.today()

                raw_curr = item.get("transactionCurrency") or item.get("transCurrency") or ""
                transaction_currency = str(raw_curr).upper()
                notes: str | None = None

                raw_tx_amount = item.get("transactionAmount") or item.get("transAmount")
                raw_basic_amount = item.get("basicAmount") or item.get("deductAmount")

                try:
                    if transaction_currency == "UAH" and raw_tx_amount is not None:
                        # Direct UAH amount — no conversion needed
                        amount = Decimal(str(raw_tx_amount))
                    else:
                        # Non-UAH purchase: convert basicAmount (USDT ≈ USD) via NBU rate
                        basic_amount = Decimal(str(raw_basic_amount or raw_tx_amount or "0"))
                        try:
                            nbu_rate = await get_usd_uah_rate(session, tx_date)
                            amount = (basic_amount * nbu_rate).quantize(Decimal("0.01"))
                        except RuntimeError as rate_exc:
                            errors.append(f"Rate lookup failed for {ext_id}: {rate_exc}")
                            skipped += 1
                            continue

                        # Preserve original amount in notes for audit
                        orig_amt = raw_tx_amount or basic_amount
                        notes = f"Original: {orig_amt} {transaction_currency}"

                    if amount <= 0:
                        skipped += 1
                        continue

                except (InvalidOperation, KeyError) as exc:
                    errors.append(f"Amount parse error for {ext_id}: {exc}")
                    skipped += 1
                    continue

                merchant = item.get("merchantName") or None
                description = merchant or f"Bybit Card {transaction_currency}"

                tx = Transaction(
                    account_id=account_id,
                    type=tx_type,
                    amount=amount,
                    description=description[:255],
                    merchant=(merchant or "")[:150] if merchant else None,
                    date=tx_date,
                    transaction_time=tx_timestamp,
                    external_id=ext_id,
                    notes=notes,
                )
                session.add(tx)
                synced += 1

            await session.flush()

            # Stop pagination when no more pages
            if not next_cursor or next_cursor == cursor or len(records) == 0:
                break
            cursor = next_cursor

    integration.last_synced_at = datetime.now(tz=timezone.utc)
    await session.commit()
    logger.info("Bybit sync complete: %d synced, %d skipped", synced, skipped)
    return IntegrationSyncResult(
        provider="bybit",
        synced_count=synced,
        skipped_count=skipped,
        error="; ".join(errors) if errors else None,
    )
