"""NBU (National Bank of Ukraine) exchange rate service.

Fetches the official USD/UAH rate for a given date from the public NBU API:
  https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&date=YYYYMMDD&json

Response shape (list with one item):
  [{"r030":840,"txt":"Долар США","rate":44.6743,"cc":"USD","exchangedate":"21.09.2026"}]

Results are persisted in the nbu_rate_cache table to avoid redundant HTTP
calls.  On network failure the service falls back to the nearest cached rate
(preferring the most recent date <= the requested date).
"""
import logging
from datetime import date as date_
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nbu_rate_cache import NbuRateCache

logger = logging.getLogger("aurum.nbu_rate")

_NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"


async def get_usd_uah_rate(session: AsyncSession, for_date: date_) -> Decimal:
    """Return the UAH rate for 1 USD on the given date.

    Priority:
    1. Already cached row for that exact date.
    2. Fresh fetch from NBU API → cache and return.
    3. On network error: nearest earlier cached rate.
    4. If no cached rate exists at all: raise RuntimeError.
    """
    # 1. Cache hit
    cached = await session.get(NbuRateCache, for_date)
    if cached is not None:
        return cached.usd_uah_rate

    # 2. Fetch from NBU
    date_str = for_date.strftime("%Y%m%d")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{_NBU_URL}?valcode=USD&date={date_str}&json")
            response.raise_for_status()
            data = response.json()

        if not data or not isinstance(data, list):
            raise ValueError(f"Unexpected NBU response: {data!r}")

        rate = Decimal(str(data[0]["rate"]))
        # Persist in cache
        row = NbuRateCache(rate_date=for_date, usd_uah_rate=rate)
        session.add(row)
        await session.flush()
        logger.info("NBU rate for %s: 1 USD = %s UAH", for_date, rate)
        return rate

    except Exception as exc:
        logger.warning("NBU API call failed for %s (%s) — falling back to cached rate", for_date, exc)

    # 3. Fallback: nearest earlier cached rate
    result = await session.execute(
        select(NbuRateCache)
        .where(NbuRateCache.rate_date <= for_date)
        .order_by(NbuRateCache.rate_date.desc())
        .limit(1)
    )
    fallback = result.scalar_one_or_none()
    if fallback is not None:
        logger.warning("Using fallback NBU rate from %s: %s", fallback.rate_date, fallback.usd_uah_rate)
        return fallback.usd_uah_rate

    raise RuntimeError(
        f"No NBU USD/UAH rate available for {for_date} and no cached fallback exists. "
        "Check network connectivity to bank.gov.ua."
    )
