from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import String, func, select
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enums import LifecycleStatus as LifecycleStatusEnum
from app.models.expense import Expense

if TYPE_CHECKING:
    from app.models.expense import Expense

# Create the enum type for casting
lifecycle_status_pg_enum = ENUM(
    *[s.value for s in LifecycleStatusEnum],
    name="lifecyclestatus",
    create_type=False
)


class ExpenseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, expense_id: UUID) -> "Expense | None":
        result = await self.session.execute(
            select(Expense)
            .options(
                selectinload(Expense.line_items),
                selectinload(Expense.vendor),
                selectinload(Expense.category),
                selectinload(Expense.project),
                selectinload(Expense.receipt),
                selectinload(Expense.source_event),
            )
            .where(Expense.id == expense_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        project_id: UUID | None = None,
        vendor_id: UUID | None = None,
        category_id: UUID | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list["Expense"]:
        query = select(Expense).options(
            selectinload(Expense.vendor),
            selectinload(Expense.category),
            selectinload(Expense.project),
            selectinload(Expense.receipt),
        )
        if project_id:
            query = query.where(Expense.project_id == project_id)
        if vendor_id:
            query = query.where(Expense.vendor_id == vendor_id)
        if category_id:
            query = query.where(Expense.category_id == category_id)
        if status:
            query = query.where(Expense.lifecycle_status.cast(String) == status)
        if date_from:
            query = query.where(Expense.transaction_date >= date_from)
        if date_to:
            query = query.where(Expense.transaction_date <= date_to)
        query = query.order_by(Expense.transaction_date.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(
        self,
        project_id: UUID | None = None,
        vendor_id: UUID | None = None,
        category_id: UUID | None = None,
        status: str | None = None,
    ) -> int:
        query = select(func.count(Expense.id))
        if project_id:
            query = query.where(Expense.project_id == project_id)
        if vendor_id:
            query = query.where(Expense.vendor_id == vendor_id)
        if category_id:
            query = query.where(Expense.category_id == category_id)
        if status:
            query = query.where(Expense.lifecycle_status.cast(String) == status)
        result = await self.session.execute(query)
        return result.scalar_one()

    async def create(self, expense: "Expense") -> "Expense":
        self.session.add(expense)
        await self.session.flush()
        return expense

    async def update(self, expense: "Expense") -> "Expense":
        await self.session.flush()
        return expense

    async def delete(self, expense: "Expense") -> None:
        await self.session.delete(expense)
        await self.session.flush()

    async def transition_status(
        self,
        expense: "Expense",
        new_status: str,
        actor_id: UUID | None = None,
        audit_event_id: UUID | None = None,
    ) -> "Expense":
        from app.models.enums import LifecycleStatus
        valid_transitions = {
            "RECEIVED": ["VALIDATED"],
            "VALIDATED": ["PROCESSING", "STAGED"],          # STAGED: skip OCR when manual
            "PROCESSING": ["EXTRACTED"],
            "EXTRACTED": ["NEEDS_CONFIRMATION", "STAGED", "RECONCILED"],  # RECONCILED: direct match
            "NEEDS_CONFIRMATION": ["STAGED", "REJECTED"],
            "STAGED": ["RECONCILING", "EXTRACTED", "RECONCILED"],  # EXTRACTED/RECONCILED shortcuts
            "RECONCILING": ["RECONCILED", "UNMATCHED", "AMBIGUOUS"],
            "RECONCILED": ["POSTED"],
            "POSTED": [],
            "FAILED": [],
            "REJECTED": [],
            "UNMATCHED": ["STAGED"],
            "AMBIGUOUS": ["STAGED"],
        }
        if expense.lifecycle_status.value not in valid_transitions:
            raise ValueError(f"Invalid current status: {expense.lifecycle_status}")
        if new_status not in valid_transitions[expense.lifecycle_status.value]:
            raise ValueError(
                f"Invalid transition from {expense.lifecycle_status} to {new_status}"
            )
        expense.lifecycle_status = LifecycleStatus(new_status)
        await self.session.flush()
        return expense
