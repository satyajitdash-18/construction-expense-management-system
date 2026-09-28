from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import PaymentMethod

if TYPE_CHECKING:
    from app.models.reconciliation_record import ReconciliationRecord
    from app.models.source_event import SourceEvent


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payee_raw_text: Mapped[str] = mapped_column(String(255), nullable=False)
    upi_reference: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    bank_reference: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method", create_constraint=True),
        nullable=False,
    )
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str] = mapped_column(String(2000), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    source_event: Mapped["SourceEvent"] = relationship(back_populates="payment_events", lazy="selectin")
    reconciliation_records: Mapped[list["ReconciliationRecord"]] = relationship(
        back_populates="payment_event", lazy="dynamic"
    )

    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<PaymentEvent(id={self.id}, amount={self.amount}, upi_ref={self.upi_reference})>"
