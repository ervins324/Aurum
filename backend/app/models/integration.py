"""Integration model — stores encrypted credentials for external bank/exchange
providers (Monobank, Bybit).  One row per provider (unique constraint on
`provider`).  Credentials are encrypted via app.core.encryption (Fernet);
they are never returned in plaintext from the API.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Integration(Base, TimestampMixin):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("provider", name="uq_integration_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    # Provider identifier: "monobank" or "bybit"
    provider: Mapped[str] = mapped_column(String(30), nullable=False)

    # Fernet-encrypted Monobank personal token (NULL for Bybit rows)
    token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fernet-encrypted Bybit API key (NULL for Monobank rows)
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fernet-encrypted Bybit API secret (NULL for Monobank rows)
    api_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The Aurum account where synced transactions land.
    # SET NULL on account deletion so we don't cascade-delete the integration.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )

    # When the last successful sync completed (UTC)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Bybit cursor for resumable cursor-based pagination
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)

    account: Mapped["Account | None"] = relationship(foreign_keys=[account_id])  # type: ignore[name-defined]
