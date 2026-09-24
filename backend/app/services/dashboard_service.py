from collections import defaultdict
import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TransactionType
from app.models.transaction import Transaction, TransactionSplit
from app.schemas.dashboard import CategoryBreakdownChildItem, CategoryBreakdownItem, DashboardSummary
from app.services.category_rollup import rollup_spending_by_top_level_category
from app.services.mcc_service import get_money_transfer_category_ids

# Categorical slots are capped at 8 (dataviz skill: a 9th series folds into "Other",
# never a generated hue) — this is also the exact size of the default category set.
MAX_CHART_SLICES = 8
OTHER_SLICE_COLOR = "#898781"  # muted ink, reserved for the non-categorical rollup


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


async def get_dashboard_summary(
    session: AsyncSession, year: int, month: int, exclude_transfers: bool = False
) -> DashboardSummary:
    start, end = _month_bounds(year, month)
    transfer_cat_ids = await get_money_transfer_category_ids(session) if exclude_transfers else set()

    if not exclude_transfers or not transfer_cat_ids:
        totals_stmt = (
            select(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.date >= start, Transaction.date <= end)
            .group_by(Transaction.type)
        )
        totals_result = await session.execute(totals_stmt)
        totals: dict[TransactionType, Decimal] = {row[0]: row[1] for row in totals_result.all()}
    else:
        split_ids_stmt = select(TransactionSplit.transaction_id).distinct()
        totals = defaultdict(Decimal)

        # Plain transactions
        plain_stmt = (
            select(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.id.not_in(split_ids_stmt),
                or_(
                    Transaction.category_id.is_(None),
                    Transaction.category_id.not_in(transfer_cat_ids),
                ),
            )
            .group_by(Transaction.type)
        )
        for tx_type, amount in (await session.execute(plain_stmt)).all():
            totals[tx_type] += amount

        # Split lines
        split_stmt = (
            select(Transaction.type, func.coalesce(func.sum(TransactionSplit.amount), 0))
            .join(Transaction, Transaction.id == TransactionSplit.transaction_id)
            .where(
                Transaction.date >= start,
                Transaction.date <= end,
                or_(
                    TransactionSplit.category_id.is_(None),
                    TransactionSplit.category_id.not_in(transfer_cat_ids),
                ),
            )
            .group_by(Transaction.type)
        )
        for tx_type, amount in (await session.execute(split_stmt)).all():
            totals[tx_type] += amount

        # Internal transfers (TransactionType.TRANSFER) don't have categories, always preserve them
        transfers_stmt = (
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.type == TransactionType.TRANSFER,
                Transaction.date >= start,
                Transaction.date <= end,
            )
        )
        totals[TransactionType.TRANSFER] = (await session.scalar(transfers_stmt)) or Decimal("0")

    real_income = totals.get(TransactionType.INCOME, Decimal("0"))
    spent = totals.get(TransactionType.EXPENSE, Decimal("0"))
    transferred_out = totals.get(TransactionType.TRANSFER, Decimal("0"))

    # A subcategory's spending rolls up into its parent's slice, and a split
    # transaction's category_id=NULL means its category lives on its split
    # lines instead — rollup_spending_by_top_level_category handles both
    # the same way a plain transaction's category already was.
    rows = await rollup_spending_by_top_level_category(
        session,
        transaction_type=TransactionType.EXPENSE,
        start_date=start,
        end_date=end,
        exclude_category_ids=transfer_cat_ids if exclude_transfers else None,
    )

    top_rows, rest_rows = rows[:MAX_CHART_SLICES], rows[MAX_CHART_SLICES:]

    def _percent(amount: Decimal) -> float:
        return float(amount / spent * 100) if spent else 0.0

    spending_by_category = [
        CategoryBreakdownItem(
            category_id=row.category_id, name=row.name, color=row.color, icon=row.icon,
            amount=row.amount, percent=_percent(row.amount),
            children=[
                CategoryBreakdownChildItem(
                    category_id=child.category_id, name=child.name, color=child.color, icon=child.icon,
                    amount=child.amount,
                )
                for child in row.children
            ],
        )
        for row in top_rows
    ]

    if rest_rows:
        other_amount = sum((row.amount for row in rest_rows), Decimal("0"))
        spending_by_category.append(
            CategoryBreakdownItem(
                category_id=None, name="Other", color=OTHER_SLICE_COLOR, icon="more-horizontal",
                amount=other_amount, percent=_percent(other_amount),
            )
        )

    return DashboardSummary(
        year=year,
        month=month,
        real_income=real_income,
        spent=spent,
        net=real_income - spent,
        transferred_out=transferred_out,
        spending_by_category=spending_by_category,
    )
