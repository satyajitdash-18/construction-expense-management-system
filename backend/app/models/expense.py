from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import LifecycleStatus, PaymentMethod

if TYPE_CHECKING:
    from app.models.evidence import Evidence
    from app.models.expense_category import ExpenseCategory
    from app.models.project import Project
    from app.models.receipt import Receipt
    from app.models.reconciliation_record import ReconciliationRecord
    from app.models.source_event import SourceEvent
    from app.models.vendor import Vendor


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expense_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    transaction_date: Mapped[date] = mapped_column(nullable=False, index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method", create_constraint=True),
        nullable=False,
        default=PaymentMethod.CASH,
    )
    gstin_supplier: Mapped[str | None] = mapped_column(String(15), nullable=True)
    hsn_sac_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cgst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    sgst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    igst_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    irn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    extraction_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default={})
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        Enum(LifecycleStatus, name="lifecycle_status", create_constraint=True),
        nullable=False,
        default=LifecycleStatus.RECEIVED,
        index=True,
    )
    receipt_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("receipts.id", ondelete="SET NULL"), nullable=True
    )
    source_audit_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    project: Mapped["Project"] = relationship(back_populates="expenses", lazy="selectin")
    source_event: Mapped["SourceEvent"] = relationship(back_populates="expenses", lazy="selectin")
    vendor: Mapped["Vendor | None"] = relationship(back_populates="expenses", lazy="selectin")
    category: Mapped["ExpenseCategory | None"] = relationship(back_populates="expenses", lazy="selectin")
    receipt: Mapped["Receipt | None"] = relationship(
        back_populates="expense", foreign_keys="Expense.receipt_id", lazy="selectin"
    )
    line_items: Mapped[list["ExpenseLineItem"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan", lazy="selectin"
    )
    reconciliation_records: Mapped[list["ReconciliationRecord"]] = relationship(
        back_populates="expense", lazy="dynamic"
    )
    evidence_files: Mapped[list["Evidence"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_expenses_project_status_date", "project_id", "lifecycle_status", "transaction_date"),
        Index("ix_expenses_vendor_date", "vendor_id", "transaction_date"),
    )

    def __repr__(self) -> str:
        return f"<Expense(id={self.id}, project_id={self.project_id}, total={self.total}, status={self.lifecycle_status})>"


class ExpenseLineItem(Base):
    __tablename__ = "expense_line_items"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    expense_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    expense: Mapped["Expense"] = relationship(back_populates="line_items", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ExpenseLineItem(id={self.id}, expense_id={self.expense_id}, amount={self.amount})>"
