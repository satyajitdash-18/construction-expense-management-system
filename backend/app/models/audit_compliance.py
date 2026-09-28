"""Audit compliance models for data retention, GDPR, and audit reporting."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ARRAY as sa_array
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import GDPRRequestStatus, GDPRRequestType

if TYPE_CHECKING:
    from app.models.user import User


class AuditReport(Base):
    """Generated audit report records."""

    __tablename__ = "audit_reports"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    date_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="json")
    include_payload: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="generating", index=True
    )
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    record_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    user: Mapped["User | None"] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_audit_reports_type_status", "report_type", "status"),
        Index("ix_audit_reports_user_date", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditReport(id={self.id}, type={self.report_type}, status={self.status})>"


class DataRetentionPolicy(Base):
    """Data retention policy configuration."""

    __tablename__ = "data_retention_policies"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    entity_types: Mapped[list[str]] = mapped_column(
        sa_array(String),
        nullable=False,
    )
    retention_days: Mapped[int] = mapped_column(nullable=False)
    archive_after_days: Mapped[int | None] = mapped_column(nullable=True)
    delete_after_days: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    def __repr__(self) -> str:
        return f"<DataRetentionPolicy(id={self.id}, name={self.name}, active={self.is_active})>"


class GDPRRequest(Base):
    """GDPR data subject request tracking."""

    __tablename__ = "gdpr_requests"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    request_type: Mapped[GDPRRequestType] = mapped_column(
        Enum(GDPRRequestType, name="gdpr_request_type", create_constraint=True),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[GDPRRequestStatus] = mapped_column(
        Enum(GDPRRequestStatus, name="gdpr_request_status", create_constraint=True),
        nullable=False,
        default=GDPRRequestStatus.PENDING,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    response_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    user: Mapped["User"] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_gdpr_requests_user_status", "user_id", "status"),
        Index("ix_gdpr_requests_email_status", "email", "status"),
    )

    def __repr__(self) -> str:
        return f"<GDPRRequest(id={self.id}, type={self.request_type}, user={self.user_id}, status={self.status})>"


class AuditReportExport(Base):
    """Temporary storage for audit report exports."""

    __tablename__ = "audit_report_exports"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    report_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("audit_reports.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    download_count: Mapped[int] = mapped_column(default=0)
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditReportExport(id={self.id}, report={self.report_id}, format={self.format})>"
