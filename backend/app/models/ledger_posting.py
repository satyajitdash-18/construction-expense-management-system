from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.audit_event import AuditEvent
    from app.models.expense import Expense
    from app.models.project import Project


class LedgerPosting(Base):
    __tablename__ = "ledger_postings"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    expense_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="POSTED")  # POSTED, REVERSED
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_audit_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=False
    )
    reversal_audit_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("audit_events.id", ondelete="RESTRICT"), nullable=True
    )

    expense: Mapped["Expense"] = relationship(lazy="selectin")
    project: Mapped["Project"] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<LedgerPosting(id={self.id}, expense_id={self.expense_id}, status={self.status})>"
