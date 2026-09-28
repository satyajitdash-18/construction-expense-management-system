from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    correlation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    causation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("audit_events.id"), nullable=True, index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default={})
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    caused_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="cause", foreign_keys="AuditEvent.causation_id", remote_side="AuditEvent.id", lazy="selectin"
    )
    cause: Mapped["AuditEvent | None"] = relationship(
        back_populates="caused_events", foreign_keys="AuditEvent.causation_id", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_audit_events_correlation_id", "correlation_id"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditEvent(id={self.id}, type={self.event_type}, entity={self.entity_type}:{self.entity_id})>"
