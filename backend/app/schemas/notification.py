"""Notification schemas for multi-channel notifications and webhooks."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl, field_validator


class NotificationTemplate(BaseModel):
    """Notification template."""

    name: str
    subject: str
    body: str
    channel: str
    variables: list[str] = Field(default_factory=list)


class NotificationCreate(BaseModel):
    """Request to create a notification."""

    user_id: UUID | None = None
    channel: str = Field(pattern="^(email|sms|whatsapp|push|webhook)$")
    subject: str | None = None
    body: str
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    metadata: dict[str, Any] | None = None
    scheduled_at: datetime | None = None


class NotificationResponse(BaseModel):
    """Notification response."""

    id: UUID
    user_id: UUID | None = None
    channel: str
    subject: str | None = None
    body: str
    status: str
    priority: str
    error_message: str | None = None
    sent_at: datetime | None = None
    created_at: datetime
    metadata: dict[str, Any] | None = Field(
        default=None, validation_alias="notification_metadata"
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class NotificationListResponse(BaseModel):
    """Paginated notification list."""

    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int


class WebhookConfigCreate(BaseModel):
    """Request to create a webhook configuration."""

    url: HttpUrl
    events: list[str] = Field(min_length=1)
    secret: str | None = None
    headers: dict[str, str] | None = None
    retry_policy: dict[str, Any] | None = None
    is_active: bool = True

    @field_validator("url")
    @classmethod
    def validate_webhook_url(cls, v: HttpUrl) -> HttpUrl:
        from app.core.security import validate_safe_webhook_url
        try:
            validate_safe_webhook_url(str(v))
        except ValueError as err:
            raise ValueError(str(err)) from err
        return v


class WebhookConfigResponse(BaseModel):
    """Webhook configuration response."""

    id: UUID
    url: str
    events: list[str]
    secret: str | None = None
    headers: dict[str, str] | None = None
    retry_policy: dict[str, Any] | None = None
    is_active: bool
    last_triggered_at: datetime | None = None
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class WebhookConfigListResponse(BaseModel):
    """Paginated webhook config list."""

    items: list[WebhookConfigResponse]
    total: int
    page: int
    page_size: int


class WebhookDeliveryResponse(BaseModel):
    """Webhook delivery attempt response."""

    id: UUID
    webhook_config_id: UUID
    event_type: str
    payload: dict[str, Any]
    response_status: int | None = None
    response_body: str | None = None
    attempt_number: int
    success: bool
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class WebhookDeliveryListResponse(BaseModel):
    """Paginated webhook delivery list."""

    items: list[WebhookDeliveryResponse]
    total: int
    page: int
    page_size: int


class NotificationPreferenceCreate(BaseModel):
    """Request to create/update notification preferences."""

    user_id: UUID
    channel: str = Field(pattern="^(email|sms|whatsapp|push|webhook)$")
    event_type: str
    enabled: bool = True
    conditions: dict[str, Any] | None = None


class NotificationPreferenceResponse(BaseModel):
    """Notification preference response."""

    id: UUID
    user_id: UUID
    channel: str
    event_type: str
    enabled: bool
    conditions: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationStats(BaseModel):
    """Notification statistics."""

    total_sent: int
    total_failed: int
    by_channel: dict[str, int]
    by_status: dict[str, int]
    by_priority: dict[str, int]
    success_rate: float
