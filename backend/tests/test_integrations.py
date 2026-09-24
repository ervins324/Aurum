"""Tests for integration routes, credential encryption/masking, and NBU rate caching."""
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.core.encryption import decrypt, encrypt, mask
from app.models.nbu_rate_cache import NbuRateCache
from app.services.nbu_rate_service import get_usd_uah_rate


def test_encryption_roundtrip():
    secret = "secret_token_12345_xyz"
    encrypted = encrypt(secret)
    assert encrypted != secret
    decrypted = decrypt(encrypted)
    assert decrypted == secret


def test_mask():
    assert mask("1234567890") == "123…890"
    assert mask("short") == "***"


@pytest.mark.asyncio
async def test_list_integrations_empty_by_default(client: AsyncClient):
    resp = await client.get("/integrations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    providers = {item["provider"] for item in data}
    assert providers == {"monobank", "bybit"}
    for item in data:
        assert item["is_configured"] is False
        assert item["token_preview"] is None
        assert item["key_preview"] is None


@pytest.mark.asyncio
async def test_set_and_delete_monobank_integration(client: AsyncClient, account_id: int):
    # Set credentials
    payload = {
        "token": "test_monobank_token_12345678",
        "account_id": account_id,
    }
    resp = await client.put("/integrations/monobank", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "monobank"
    assert data["is_configured"] is True
    assert data["token_preview"] == "tes…678"
    assert data["account_id"] == account_id

    # Verify GET returns masked preview, not raw token
    list_resp = await client.get("/integrations")
    mono = next(item for item in list_resp.json() if item["provider"] == "monobank")
    assert mono["is_configured"] is True
    assert mono["token_preview"] == "tes…678"

    # Delete
    del_resp = await client.delete("/integrations/monobank")
    assert del_resp.status_code == 204

    # Verify unconfigured again
    list_resp2 = await client.get("/integrations")
    mono2 = next(item for item in list_resp2.json() if item["provider"] == "monobank")
    assert mono2["is_configured"] is False


@pytest.mark.asyncio
async def test_set_and_delete_bybit_integration(client: AsyncClient, account_id: int):
    payload = {
        "api_key": "my_bybit_api_key_xyz",
        "api_secret": "my_bybit_api_secret_secret",
        "account_id": account_id,
    }
    resp = await client.put("/integrations/bybit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "bybit"
    assert data["is_configured"] is True
    assert data["key_preview"] == "my_…xyz"

    del_resp = await client.delete("/integrations/bybit")
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_nbu_rate_service_caches_and_returns(test_sessionmaker):
    test_date = date(2026, 1, 15)
    async with test_sessionmaker() as session:
        # Pre-seed cache
        session.add(NbuRateCache(rate_date=test_date, usd_uah_rate=Decimal("43.500000")))
        await session.commit()

        rate = await get_usd_uah_rate(session, test_date)
        assert rate == Decimal("43.500000")


@pytest.mark.asyncio
async def test_mcc_category_resolution(test_sessionmaker, categories: dict):
    from app.models.enums import TransactionType
    from app.services.mcc_service import resolve_category_id_by_mcc

    from app.services.mcc_service import resolve_fallback_other_category

    async with test_sessionmaker() as session:
        # 5411 is Groceries (seeded in categories fixture)
        cat_id = await resolve_category_id_by_mcc(session, 5411, TransactionType.EXPENSE)
        assert cat_id is not None
        assert cat_id == categories["Groceries"]["id"]

        # 5812 is Dining Out
        cat_id_dining = await resolve_category_id_by_mcc(session, 5812, TransactionType.EXPENSE)
        assert cat_id_dining is not None
        assert cat_id_dining == categories["Dining Out"]["id"]

        # 4215 and 9402 map to ("Logistics", "Transportation") -> matches Transportation
        cat_id_logistics = await resolve_category_id_by_mcc(session, 4215, TransactionType.EXPENSE)
        if "Transportation" in categories:
            assert cat_id_logistics == categories["Transportation"]["id"]
        cat_id_postal = await resolve_category_id_by_mcc(session, 9402, TransactionType.EXPENSE)
        if "Transportation" in categories:
            assert cat_id_postal == categories["Transportation"]["id"]

        # 4829 now resolves to the seeded "Money Transfers" expense category.
        # Looked up directly by name+kind since the categories fixture dict
        # deduplicates by name when both an expense and income category share it.
        from sqlalchemy import select as sa_select
        from app.models.category import Category
        from app.models.enums import CategoryKind
        expense_transfers_row = await session.execute(
            sa_select(Category.id).where(
                Category.name == "Money Transfers",
                Category.kind == CategoryKind.EXPENSE,
            ).limit(1)
        )
        expense_transfers_id = expense_transfers_row.scalar_one_or_none()
        assert expense_transfers_id is not None, "Seeded 'Money Transfers' EXPENSE category must exist"

        cat_id_transfers = await resolve_category_id_by_mcc(session, 4829, TransactionType.EXPENSE)
        assert cat_id_transfers is not None
        assert cat_id_transfers == expense_transfers_id

        # Income-side MCC 4829 resolution uses the seeded income "Money Transfers" category
        income_transfers_row = await session.execute(
            sa_select(Category.id).where(
                Category.name == "Money Transfers",
                Category.kind == CategoryKind.INCOME,
            ).limit(1)
        )
        income_transfers_id = income_transfers_row.scalar_one_or_none()
        assert income_transfers_id is not None, "Seeded 'Money Transfers' INCOME category must exist"

        cat_id_transfers_income = await resolve_category_id_by_mcc(session, 4829, TransactionType.INCOME)
        assert cat_id_transfers_income is not None
        assert cat_id_transfers_income == income_transfers_id

        # Create custom categories to test 6012, 8999 resolution
        custom_finance = Category(name="Finance", kind=CategoryKind.EXPENSE, color="#234567", is_default=False)
        custom_prof = Category(name="Professional Services", kind=CategoryKind.EXPENSE, color="#345678", is_default=False)
        session.add_all([custom_finance, custom_prof])
        await session.commit()

        assert await resolve_category_id_by_mcc(session, 6012, TransactionType.EXPENSE) == custom_finance.id
        assert await resolve_category_id_by_mcc(session, 8999, TransactionType.EXPENSE) == custom_prof.id

        # Fallback category resolves or creates Other
        fallback_id = await resolve_fallback_other_category(session, TransactionType.EXPENSE)
        assert fallback_id is not None

        # Unknown or None MCC returns None (before fallback is applied)
        assert await resolve_category_id_by_mcc(session, 99999, TransactionType.EXPENSE) is None
        assert await resolve_category_id_by_mcc(session, None, TransactionType.EXPENSE) is None


@pytest.mark.asyncio
async def test_monobank_sync_period_payload(client: AsyncClient):
    payload = {
        "sync_from": "2026-09-01",
        "sync_to": "2026-09-20",
    }
    resp = await client.post("/integrations/monobank/sync", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "monobank"
    assert data["error"] == "Not configured"


@pytest.mark.asyncio
async def test_transaction_time_storage_and_filtering(client: AsyncClient, account_id: int):
    from datetime import datetime, timezone

    # Create two transactions on the same day with different transaction_time
    morning_dt = "2026-09-24T09:30:00Z"
    evening_dt = "2026-09-24T18:45:00Z"

    tx1_resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "25.00",
            "description": "Morning coffee",
            "date": "2026-09-24",
            "transaction_time": morning_dt,
        },
    )
    assert tx1_resp.status_code == 201
    tx1_data = tx1_resp.json()
    assert tx1_data["transaction_time"] is not None

    tx2_resp = await client.post(
        "/transactions",
        json={
            "account_id": account_id,
            "type": "expense",
            "amount": "75.00",
            "description": "Evening dinner",
            "date": "2026-09-24",
            "transaction_time": evening_dt,
        },
    )
    assert tx2_resp.status_code == 201

    # Test date_desc sort (evening before morning on same date)
    desc_resp = await client.get("/transactions?start_date=2026-09-24&end_date=2026-09-24&sort=date_desc")
    assert desc_resp.status_code == 200
    items_desc = desc_resp.json()["items"]
    assert len(items_desc) == 2
    assert items_desc[0]["description"] == "Evening dinner"
    assert items_desc[1]["description"] == "Morning coffee"

    # Test date_asc sort (morning before evening on same date)
    asc_resp = await client.get("/transactions?start_date=2026-09-24&end_date=2026-09-24&sort=date_asc")
    assert asc_resp.status_code == 200
    items_asc = asc_resp.json()["items"]
    assert len(items_asc) == 2
    assert items_asc[0]["description"] == "Morning coffee"
    assert items_asc[1]["description"] == "Evening dinner"

    # Test start_time filter (filter after 12:00 -> only Evening dinner)
    time_filtered = await client.get("/transactions?start_date=2026-09-24&end_date=2026-09-24&start_time=12:00:00")
    assert time_filtered.status_code == 200
    items_time = time_filtered.json()["items"]
    assert len(items_time) == 1
    assert items_time[0]["description"] == "Evening dinner"

    # Test editing transaction_time via PATCH
    updated_dt = "2026-09-24T12:00:00Z"
    patch_resp = await client.patch(
        f"/transactions/{tx1_data['id']}",
        json={"transaction_time": updated_dt},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["transaction_time"] is not None

    # Test clearing transaction_time via PATCH
    clear_resp = await client.patch(
        f"/transactions/{tx1_data['id']}",
        json={"transaction_time": None},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["transaction_time"] is None

