"""Notification API endpoints for multi-channel notifications and webhooks."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as get_db_dep
from app.core.dependencies import (
    get_current_user as get_current_user_dep,
    require_admin,
    require_roles,
)
from app.models.user import User
from app.schemas.notification import (
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    WebhookConfigCreate,
    WebhookConfigListResponse,
    WebhookConfigResponse,
    WebhookDeliveryListResponse,
    WebhookDeliveryResponse,
)
from app.services.notification import create_notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def create_notification(
    request: NotificationCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> NotificationResponse:
    """Create and send a notification."""
    user_roles = {r.name for r in current_user.roles}
    if "admin" not in user_roles and request.user_id and request.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot send notifications to other users without admin privileges",
        )

    notification_service = create_notification_service(db)

    notification_id = await notification_service.send_notification(
        channel=request.channel,
        subject=request.subject,
        body=request.body,
        user_id=request.user_id or current_user.id,
        priority=request.priority,
        metadata=request.metadata,
        scheduled_at=request.scheduled_at,
    )

    from app.models.notification import Notification
    notification = await db.get(Notification, notification_id)
    return NotificationResponse.model_validate(notification)


@router.post("/bulk", response_model=list[NotificationResponse], status_code=status.HTTP_201_CREATED)
async def create_bulk_notifications(
    user_ids: list[UUID],
    channel: str,
    body: str,
    subject: str | None = None,
    priority: str = "normal",
    metadata: dict[str, Any] | None = None,
    current_user: User = Depends(require_roles("admin", "project_manager")),
    db: AsyncSession = Depends(get_db_dep),
) -> list[NotificationResponse]:
    """Send notification to multiple users."""
    notification_service = create_notification_service(db)

    notification_ids = await notification_service.send_bulk_notification(
        user_ids=user_ids,
        channel=channel,
        subject=subject,
        body=body,
        priority=priority,
        metadata=metadata,
    )

    from app.models.notification import Notification
    notifications = []
    for nid in notification_ids:
        notification = await db.get(Notification, nid)
        if notification:
            notifications.append(NotificationResponse.model_validate(notification))
    return notifications


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> NotificationListResponse:
    """List notifications for current user."""
    notification_service = create_notification_service(db)
    result = await notification_service.get_user_notifications(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/stats", response_model=dict)
async def get_notification_stats(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """Get notification statistics."""
    notification_service = create_notification_service(db)
    stats = await notification_service.get_notification_stats()
    return stats


@router.post("/process-scheduled", response_model=dict)
async def process_scheduled_notifications(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """Process scheduled notifications that are due."""
    notification_service = create_notification_service(db)
    sent_count = await notification_service.process_scheduled_notifications()
    return {"sent_count": sent_count, "timestamp": datetime.now().isoformat()}


# Webhook Config endpoints
@router.post("/webhooks", response_model=WebhookConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    request: WebhookConfigCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> WebhookConfigResponse:
    """Create a webhook configuration."""
    notification_service = create_notification_service(db)
    webhook = await notification_service.create_webhook_config(
        url=str(request.url),
        events=request.events,
        secret=request.secret,
        headers=request.headers,
        retry_policy=request.retry_policy,
        is_active=request.is_active,
    )
    return WebhookConfigResponse.model_validate(webhook)


@router.get("/webhooks", response_model=WebhookConfigListResponse)
async def list_webhooks(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> WebhookConfigListResponse:
    """List webhook configurations."""
    notification_service = create_notification_service(db)
    result = await notification_service.list_webhook_configs(
        page=page,
        page_size=page_size,
    )

    return WebhookConfigListResponse(
        items=[WebhookConfigResponse.model_validate(w) for w in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/webhooks/{webhook_id}", response_model=WebhookConfigResponse)
async def get_webhook(
    webhook_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> WebhookConfigResponse:
    """Get webhook configuration by ID."""
    from app.models.notification import WebhookConfig
    webhook = await db.get(WebhookConfig, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return WebhookConfigResponse.model_validate(webhook)


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> None:
    """Delete a webhook configuration."""
    from app.models.notification import WebhookConfig
    webhook = await db.get(WebhookConfig, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(webhook)
    await db.commit()


@router.get("/webhooks/{webhook_id}/deliveries", response_model=WebhookDeliveryListResponse)
async def list_webhook_deliveries(
    webhook_id: UUID,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_dep),
) -> WebhookDeliveryListResponse:
    """List webhook delivery attempts."""
    notification_service = create_notification_service(db)
    result = await notification_service.get_webhook_deliveries(
        webhook_config_id=webhook_id,
        page=page,
        page_size=page_size,
    )

    return WebhookDeliveryListResponse(
        items=[WebhookDeliveryResponse.model_validate(d) for d in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


# Notification Preference endpoints (bulk PATCH/GET style)

class _BulkPreferences(BaseModel):
    """Simple preference payload accepted / returned by PATCH+GET /preferences."""
    email_enabled: bool = True
    sms_enabled: bool = False
    push_enabled: bool = True
    webhook_enabled: bool = False
    event_types: list[str] = []


@router.patch("/preferences", response_model=dict)
async def update_preferences(
    prefs: _BulkPreferences,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """Bulk-update notification preferences for the current user."""
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.notification import NotificationPreference

    channel_map = {
        "email": prefs.email_enabled,
        "sms": prefs.sms_enabled,
        "push": prefs.push_enabled,
        "webhook": prefs.webhook_enabled,
    }
    for channel, enabled in channel_map.items():
        stmt = pg_insert(NotificationPreference).values(
            user_id=current_user.id,
            channel=channel,
            event_type="ALL",
            enabled=enabled,
        ).on_conflict_do_update(
            index_elements=["user_id", "channel", "event_type"],
            set_={"enabled": enabled},
        )
        await db.execute(stmt)
    await db.commit()
    return prefs.model_dump()


@router.get("/preferences", response_model=dict)
async def get_preferences(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db_dep),
) -> dict:
    """Get notification preferences for the current user."""
    from sqlalchemy import select

    from app.models.notification import NotificationPreference

    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == current_user.id,
            NotificationPreference.event_type == "ALL",
        )
    )
    rows = result.scalars().all()
    channel_map: dict[str, bool] = {r.channel: r.enabled for r in rows}
    return _BulkPreferences(
        email_enabled=channel_map.get("email", True),
        sms_enabled=channel_map.get("sms", False),
        push_enabled=channel_map.get("push", True),
        webhook_enabled=channel_map.get("webhook", False),
    ).model_dump()

