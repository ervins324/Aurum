"""NBU exchange rate cache — avoids redundant calls to the National Bank of
Ukraine's public API when converting Bybit USD amounts to UAH.  One row per
calendar date; the primary key *is* the date (no surrogate needed)."""
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import Date, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NbuRateCache(Base):
    __tablename__ = "nbu_rate_cache"

    # The calendar date this rate applies to (UTC trading date)
    rate_date: Mapped[date_] = mapped_column(Date, primary_key=True)

    # UAH per 1 USD as published by the NBU for that date
    usd_uah_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
