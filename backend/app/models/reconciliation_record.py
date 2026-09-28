from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import MatchBasis, ReconciliationStatus

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.payment_event import PaymentEvent
    from app.models.user import User


class ReconciliationRecord(Base):
    __tablename__ = "reconciliation_records"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    expense_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payment_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[ReconciliationStatus] = mapped_column(
        Enum(ReconciliationStatus, name="reconciliation_status", create_constraint=True),
        nullable=False,
        default=ReconciliationStatus.UNMATCHED,
        index=True,
    )
    match_basis: Mapped[MatchBasis | None] = mapped_column(
        Enum(MatchBasis, name="match_basis", create_constraint=True),
        nullable=True,
    )
    match_score: Mapped[float | None] = mapped_column(nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    expense: Mapped["Expense"] = relationship(back_populates="reconciliation_records", lazy="selectin")
    payment_event: Mapped["PaymentEvent | None"] = relationship(
        back_populates="reconciliation_records", lazy="selectin"
    )
    resolver: Mapped["User | None"] = relationship(lazy="selectin")

    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<ReconciliationRecord(id={self.id}, expense={self.expense_id}, payment={self.payment_event_id}, status={self.status})>"
