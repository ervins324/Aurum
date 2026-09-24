"""add integrations, nbu_rate_cache, and external_id on transactions

Revision ID: a9c3f1e7b024
Revises: 3b7c941bbadf
Create Date: 2026-09-19 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c3f1e7b024"
down_revision: Union[str, None] = "d1a6f4c8b729"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- integrations table --
    op.create_table(
        "integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("token_enc", sa.Text(), nullable=True),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
        sa.Column("api_secret_enc", sa.Text(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", name="uq_integration_provider"),
    )

    # -- NBU rate cache table --
    op.create_table(
        "nbu_rate_cache",
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("usd_uah_rate", sa.Numeric(14, 6), nullable=False),
        sa.PrimaryKeyConstraint("rate_date"),
    )

    # -- external_id on transactions for deduplication during bank sync --
    op.add_column(
        "transactions",
        sa.Column("external_id", sa.String(100), nullable=True),
    )
    op.create_unique_constraint("uq_transaction_external_id", "transactions", ["external_id"])
    op.create_index("ix_transaction_external_id", "transactions", ["external_id"])


def downgrade() -> None:
    op.drop_index("ix_transaction_external_id", table_name="transactions")
    op.drop_constraint("uq_transaction_external_id", "transactions", type_="unique")
    op.drop_column("transactions", "external_id")
    op.drop_table("nbu_rate_cache")
    op.drop_table("integrations")
