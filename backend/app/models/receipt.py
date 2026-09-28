from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.source_event import SourceEvent


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_events.id", ondelete="CASCADE"), nullable=False
    )
    expense_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source_event: Mapped["SourceEvent"] = relationship(back_populates="receipts", lazy="selectin")
    expense: Mapped["Expense | None"] = relationship(
        back_populates="receipt", foreign_keys="Expense.receipt_id", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Receipt(id={self.id}, source_event_id={self.source_event_id}, key={self.storage_key})>"
