"""Notification models for multi-channel notifications and webhooks."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ARRAY as sa_array
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import NotificationChannel, NotificationStatus

if TYPE_CHECKING:
    from app.models.user import User


class Notification(Base):
    """Notification record for multi-channel delivery."""

    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", create_constraint=True),
        nullable=False,
        index=True,
    )
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(String(10000), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status", create_constraint=True),
        nullable=False,
        default=NotificationStatus.PENDING,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    notification_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    user: Mapped["User | None"] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_notifications_user_status", "user_id", "status"),
        Index("ix_notifications_scheduled", "scheduled_at", "status"),
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, channel={self.channel}, status={self.status})>"


class WebhookConfig(Base):
    """Webhook configuration for event delivery."""

    __tablename__ = "webhook_configs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    events: Mapped[list[str]] = mapped_column(
        sa_array(String),
        nullable=False,
    )
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    headers: Mapped[dict[str, str] | None] = mapped_column(
        JSONB, nullable=True
    )
    retry_policy: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    success_count: Mapped[int] = mapped_column(default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="config", cascade="all, delete-orphan", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<WebhookConfig(id={self.id}, url={self.url}, active={self.is_active})>"


class WebhookDelivery(Base):
    """Webhook delivery attempt record."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    webhook_config_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("webhook_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_status: Mapped[int | None] = mapped_column(nullable=True)
    response_body: Mapped[str | None] = mapped_column(String(5000), nullable=True)
    attempt_number: Mapped[int] = mapped_column(default=1, nullable=False)
    success: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    config: Mapped["WebhookConfig"] = relationship(back_populates="deliveries", lazy="selectin")

    __table_args__ = (
        Index("ix_webhook_deliveries_webhook_status", "webhook_config_id", "success"),
    )

    def __repr__(self) -> str:
        return f"<WebhookDelivery(id={self.id}, webhook={self.webhook_config_id}, success={self.success})>"


class NotificationPreference(Base):
    """User notification preferences."""

    __tablename__ = "notification_preferences"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    conditions: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(UTC), nullable=True
    )

    user: Mapped["User"] = relationship(lazy="selectin")

    __table_args__ = (
        Index("ix_notification_prefs_user_channel", "user_id", "channel", "event_type", unique=True),
    )

    def __repr__(self) -> str:
        return f"<NotificationPreference(user={self.user_id}, channel={self.channel}, enabled={self.enabled})>"
