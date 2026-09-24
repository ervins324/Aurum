"""add transaction_time column

Revision ID: a1b2c3d4e5f6
Revises: f6a4d8b2e017
Create Date: 2026-09-24 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'a9c3f1e7b024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Precise timestamp from bank APIs (UTC). NULL for manually-entered
    # transactions and all pre-existing rows.
    op.add_column(
        "transactions",
        sa.Column("transaction_time", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "transaction_time")
