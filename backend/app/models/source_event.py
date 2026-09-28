from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import SourceType

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.payment_event import PaymentEvent
    from app.models.receipt import Receipt


class SourceEvent(Base):
    __tablename__ = "source_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", create_constraint=True),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default={})
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    expenses: Mapped[list["Expense"]] = relationship(back_populates="source_event", lazy="dynamic")
    payment_events: Mapped[list["PaymentEvent"]] = relationship(
        back_populates="source_event", lazy="dynamic"
    )
    receipts: Mapped[list["Receipt"]] = relationship(back_populates="source_event", lazy="dynamic")

    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<SourceEvent(id={self.id}, source={self.source}, external_id={self.external_id})>"
