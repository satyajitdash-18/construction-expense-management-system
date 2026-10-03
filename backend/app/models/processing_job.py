from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import JobStatus, JobType


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, name="job_type", create_constraint=True),
        nullable=False,
        index=True,
    )
    source_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", create_constraint=True),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    attempts: Mapped[list["JobAttempt"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = ()

    @property
    def error_message(self) -> str | None:
        try:
            attempts = getattr(self, "attempts", None)
            if attempts:
                return attempts[-1].error_message
        except Exception:
            pass
        return None

    @property
    def completed_at(self) -> datetime | None:
        if self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            return self.updated_at
        return None

    def __repr__(self) -> str:
        return f"<ProcessingJob(id={self.id}, type={self.job_type}, status={self.status})>"


class JobAttempt(Base):
    __tablename__ = "job_attempts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    processing_job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("processing_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    job: Mapped["ProcessingJob"] = relationship(back_populates="attempts", lazy="selectin")

    def __repr__(self) -> str:
        return f"<JobAttempt(id={self.id}, job={self.processing_job_id}, attempt={self.attempt_number})>"
