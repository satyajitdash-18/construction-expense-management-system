"""Reconciliation repository for expense-payment matching."""

import builtins
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import LifecycleStatus as LifecycleStatusEnum
from app.models.enums import MatchBasis as MatchBasisEnum
from app.models.enums import ReconciliationStatus as ReconciliationStatusEnum
from app.models.expense import Expense
from app.models.payment_event import PaymentEvent
from app.models.reconciliation_record import ReconciliationRecord

if TYPE_CHECKING:
    pass


# Create enum types for casting
reconciliation_status_pg_enum = ENUM(
    *[s.value for s in ReconciliationStatusEnum],
    name="reconciliation_status",
    create_type=False,
)

match_basis_pg_enum = ENUM(
    *[s.value for s in MatchBasisEnum],
    name="match_basis",
    create_type=False,
)

lifecycle_status_pg_enum = ENUM(
    *[s.value for s in LifecycleStatusEnum],
    name="lifecycle_status",
    create_type=False,
)


class ReconciliationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, reconciliation_id: UUID) -> ReconciliationRecord | None:
        result = await self.session.execute(
            select(ReconciliationRecord)
            .options(
                selectinload(ReconciliationRecord.expense).selectinload(Expense.vendor),
                selectinload(ReconciliationRecord.payment_event),
                selectinload(ReconciliationRecord.resolver),
            )
            .where(ReconciliationRecord.id == reconciliation_id)
        )
        return result.scalar_one_or_none()

    async def get_by_expense_id(self, expense_id: UUID) -> ReconciliationRecord | None:
        result = await self.session.execute(
            select(ReconciliationRecord).where(ReconciliationRecord.expense_id == expense_id)
        )
        return result.scalar_one_or_none()

    async def get_by_payment_event_id(self, payment_event_id: UUID) -> ReconciliationRecord | None:
        result = await self.session.execute(
            select(ReconciliationRecord).where(ReconciliationRecord.payment_event_id == payment_event_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        status_filter: str | None = None,
        project_id: UUID | None = None,
        expense_id: UUID | None = None,
        payment_event_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list["ReconciliationRecord"]:
        query = (
            select(ReconciliationRecord)
            .options(
                selectinload(ReconciliationRecord.expense).selectinload(Expense.vendor),
                selectinload(ReconciliationRecord.payment_event),
                selectinload(ReconciliationRecord.resolver),
            )
            .order_by(ReconciliationRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if status_filter:
            query = query.where(
                ReconciliationRecord.status == ReconciliationStatusEnum(status_filter)
            )
        if project_id:
            query = query.join(Expense).where(Expense.project_id == project_id)
        if expense_id:
            query = query.where(ReconciliationRecord.expense_id == expense_id)
        if payment_event_id:
            query = query.where(ReconciliationRecord.payment_event_id == payment_event_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        status_filter: str | None = None,
        project_id: UUID | None = None,
    ) -> int:
        query = select(func.count(ReconciliationRecord.id))

        if status_filter:
            query = query.where(ReconciliationRecord.status == ReconciliationStatusEnum(status_filter))
        if project_id:
            query = query.join(Expense).where(Expense.project_id == project_id)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def create(self, reconciliation: ReconciliationRecord) -> ReconciliationRecord:
        self.session.add(reconciliation)
        await self.session.flush()
        return reconciliation

    async def update(self, reconciliation: ReconciliationRecord) -> ReconciliationRecord:
        await self.session.flush()
        return reconciliation

    async def get_unmatched_expenses(
        self,
        project_id: UUID | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> builtins.list["Expense"]:
        """Get expenses that are STAGED or RECONCILED but not yet reconciled."""
        query = (
            select(Expense)
            .options(
                selectinload(Expense.vendor),
                selectinload(Expense.source_event),
            )
            .where(
                Expense.lifecycle_status.cast(String).in_(
                    [LifecycleStatusEnum.STAGED.value, LifecycleStatusEnum.RECONCILED.value]
                )
            )
            .where(~Expense.reconciliation_records.any())
        )

        if project_id:
            query = query.where(Expense.project_id == project_id)
        if date_from:
            query = query.where(Expense.transaction_date >= date_from)
        if date_to:
            query = query.where(Expense.transaction_date <= date_to)

        query = query.order_by(Expense.transaction_date.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_unmatched_payment_events(
        self,
        project_id: UUID | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> builtins.list["PaymentEvent"]:
        """Get payment events that are not yet reconciled."""
        query = (
            select(PaymentEvent)
            .where(~PaymentEvent.reconciliation_records.any())
        )

        # Note: PaymentEvent is an external bank/UPI feed and is not pre-assigned to a project.
        # Project scoping occurs when payment events are reconciled with expenses.
        if date_from:
            query = query.where(PaymentEvent.occurred_at >= date_from)
        if date_to:
            query = query.where(PaymentEvent.occurred_at <= date_to)

        query = query.order_by(PaymentEvent.occurred_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def find_candidates_for_expense(
        self,
        expense: Expense,
        amount_tolerance: float = 0.01,
        date_window_days: int = 3,
    ) -> builtins.list["PaymentEvent"]:
        """Find payment event candidates for an expense based on amount and date proximity."""
        from datetime import timedelta

        min_amount = float(expense.total) - amount_tolerance
        max_amount = float(expense.total) + amount_tolerance
        min_date = expense.transaction_date - timedelta(days=date_window_days)
        max_date = expense.transaction_date + timedelta(days=date_window_days)

        query = (
            select(PaymentEvent)
            .where(
                and_(
                    PaymentEvent.amount >= min_amount,
                    PaymentEvent.amount <= max_amount,
                    PaymentEvent.occurred_at >= min_date,
                    PaymentEvent.occurred_at <= max_date,
                    ~PaymentEvent.reconciliation_records.any(),
                )
            )
            .order_by(PaymentEvent.occurred_at)
        )

        if expense.vendor_id and expense.vendor:
            query = query.where(PaymentEvent.payee_raw_text.ilike(f"%{expense.vendor.name}%"))

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def find_exact_reference_match(self, expense: Expense) -> PaymentEvent | None:
        """Find exact UPI or bank reference match (Tier 1)."""
        query = select(PaymentEvent).where(
            and_(
                or_(
                    PaymentEvent.upi_reference == expense.extraction_payload.get("upi_reference"),
                    PaymentEvent.bank_reference == expense.extraction_payload.get("bank_reference"),
                ),
                ~PaymentEvent.reconciliation_records.any(),
            )
        )

        if expense.extraction_payload.get("upi_reference"):
            query = query.where(
                PaymentEvent.upi_reference == expense.extraction_payload.get("upi_reference")
            )
        elif expense.extraction_payload.get("bank_reference"):
            query = query.where(
                PaymentEvent.bank_reference == expense.extraction_payload.get("bank_reference")
            )
        else:
            return None

        result = await self.session.execute(query)
        return result.scalars().first()
