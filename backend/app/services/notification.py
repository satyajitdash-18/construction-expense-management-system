"""Notification service for multi-channel notifications and webhooks."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.notification import (
    Notification,
    NotificationPreference,
    NotificationStatus,
    WebhookConfig,
    WebhookDelivery,
)

logger = get_logger(__name__)


class NotificationService:
    """Service for sending notifications across multiple channels."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def send_notification(
        self,
        channel: str,
        subject: str | None,
        body: str,
        user_id: UUID | None = None,
        priority: str = "normal",
        metadata: dict[str, Any] | None = None,
        scheduled_at: datetime | None = None,
    ) -> UUID:
        """Send a notification via the specified channel."""
        notification = Notification(
            user_id=user_id,
            channel=channel,
            subject=subject,
            body=body,
            priority=priority,
            metadata=metadata or {},
            status="pending",
            scheduled_at=scheduled_at,
        )
        self.db.add(notification)
        await self.db.flush()

        if scheduled_at and scheduled_at > datetime.now(UTC):
            return notification.id

        # Send immediately
        success = await self._send_via_channel(notification)
        notification.status = NotificationStatus.SENT if success else NotificationStatus.FAILED
        if success:
            notification.sent_at = datetime.now(UTC)
        else:
            notification.error_message = "Failed to send notification"

        await self.db.commit()
        return notification.id

    async def _send_via_channel(self, notification: "Notification") -> bool:
        """Send notification via the appropriate channel."""
        try:
            if notification.channel == "email":
                return await self._send_email(notification)
            elif notification.channel == "sms":
                return await self._send_sms(notification)
            elif notification.channel == "whatsapp":
                return await self._send_whatsapp(notification)
            elif notification.channel == "push":
                return await self._send_push(notification)
            elif notification.channel == "webhook":
                return await self._trigger_webhooks(notification)
            else:
                logger.warning("Unknown notification channel", channel=notification.channel)
                return False
        except Exception as e:
            logger.error("Failed to send notification", notification_id=str(notification.id), error=str(e))
            return False

    async def _send_email(self, notification: "Notification") -> bool:
        """Send email notification."""
        # TODO: Implement actual email sending (SMTP, SendGrid, etc.)
        logger.info("Email sent", user_id=str(notification.user_id), subject=notification.subject)
        return True

    async def _send_sms(self, notification: "Notification") -> bool:
        """Send SMS notification."""
        # TODO: Implement actual SMS sending (Twilio, etc.)
        logger.info("SMS sent", user_id=str(notification.user_id))
        return True

    async def _send_whatsapp(self, notification: "Notification") -> bool:
        """Send WhatsApp notification."""
        # TODO: Implement actual WhatsApp sending (WhatsApp Business API)
        logger.info("WhatsApp sent", user_id=str(notification.user_id))
        return True

    async def _send_push(self, notification: "Notification") -> bool:
        """Send push notification."""
        # TODO: Implement push notification (Firebase, APNs)
        logger.info("Push sent", user_id=str(notification.user_id))
        return True

    async def _trigger_webhooks(self, notification: "Notification") -> bool:
        """Trigger webhooks for the notification event."""
        # Find active webhook configs matching the event
        result = await self.db.execute(
            select(WebhookConfig).where(
                WebhookConfig.is_active,
                WebhookConfig.events.contains(["notification.*"]),  # Generic event match
            )
        )
        webhooks = result.scalars().all()

        if not webhooks:
            return True

        payload = {
            "event": "notification",
            "notification": {
                "id": str(notification.id),
                "user_id": str(notification.user_id) if notification.user_id else None,
                "channel": notification.channel,
                "subject": notification.subject,
                "body": notification.body,
                "priority": notification.priority,
                "metadata": notification.metadata,
                "created_at": notification.created_at.isoformat() if notification.created_at else None,
            },
        }

        success_count = 0
        for webhook in webhooks:
            success = await self._deliver_webhook(webhook, "notification.*", payload)
            if success:
                success_count += 1

        return success_count > 0

    async def _deliver_webhook(
        self,
        webhook: "WebhookConfig",
        event_type: str,
        payload: dict[str, Any],
    ) -> bool:
        """Deliver a webhook with retry logic."""
        retry_policy = webhook.retry_policy or {
            "max_attempts": 3,
            "initial_delay_seconds": 5,
            "max_delay_seconds": 300,
            "backoff_multiplier": 2,
        }

        max_attempts = retry_policy.get("max_attempts", 3)
        initial_delay = retry_policy.get("initial_delay_seconds", 5)
        max_delay = retry_policy.get("max_delay_seconds", 300)
        backoff = retry_policy.get("backoff_multiplier", 2)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ConstructionExpenseWebhook/1.0",
            **(webhook.headers or {}),
        }

        if webhook.secret:
            import hashlib
            import hmac
            signature = hmac.new(
                webhook.secret.encode(),
                json.dumps(payload).encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = signature

        delivery = WebhookDelivery(
            webhook_config_id=webhook.id,
            event_type="notification.*",
            payload=payload,
            attempt_number=0,
        )
        self.db.add(delivery)
        await self.db.flush()

        from app.core.security import validate_safe_webhook_url
        try:
            validate_safe_webhook_url(str(webhook.url))
        except ValueError as e:
            logger.error("Blocked unsafe webhook target", webhook_id=str(webhook.id), error=str(e))
            delivery.error_message = f"SSRF blocked: {e}"
            delivery.success = False
            delivery.completed_at = datetime.now(UTC)
            webhook.failure_count += 1
            await self.db.commit()
            return False

        for attempt in range(1, max_attempts + 1):
            delivery.attempt_number = attempt
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        str(webhook.url),
                        json=payload,
                        headers=headers,
                    )
                    delivery.response_status = response.status_code
                    delivery.response_body = response.text[:1000] if response.text else None

                    if 200 <= response.status_code < 300:
                        delivery.success = True
                        delivery.completed_at = datetime.now(UTC)
                        webhook.success_count += 1
                        webhook.last_triggered_at = datetime.now(UTC)
                        await self.db.commit()
                        return True
                    else:
                        delivery.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
            except Exception as e:
                delivery.error_message = str(e)

            if attempt < max_attempts:
                delay = min(initial_delay * (backoff ** (attempt - 1)), max_delay)
                logger.warning(
                    "Webhook delivery failed, retrying",
                    webhook_id=str(webhook.id),
                    attempt=attempt,
                    delay=delay,
                    error=delivery.error_message,
                )
                import asyncio
                await asyncio.sleep(delay)

        # All attempts failed
        delivery.success = False
        delivery.completed_at = datetime.now(UTC)
        webhook.failure_count += 1
        await self.db.commit()
        return False

    async def send_bulk_notification(
        self,
        user_ids: list[UUID],
        channel: str,
        subject: str | None,
        body: str,
        priority: str = "normal",
        metadata: dict[str, Any] | None = None,
    ) -> list[UUID]:
        """Send notification to multiple users."""
        notification_ids = []
        for user_id in user_ids:
            notification_id = await self.send_notification(
                channel=channel,
                subject=subject,
                body=body,
                user_id=user_id,
                priority=priority,
                metadata=metadata,
            )
            notification_ids.append(notification_id)
        return notification_ids

    async def get_user_notifications(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
    ) -> dict[str, Any]:
        """Get notifications for a user."""
        query = select(Notification).where(Notification.user_id == user_id)

        if status_filter:
            query = query.where(Notification.status == status_filter)

        # Total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Notification.created_at.desc())

        result = await self.db.execute(query)
        notifications = result.scalars().all()

        return {
            "items": notifications,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def create_webhook_config(
        self,
        url: str,
        events: list[str],
        secret: str | None = None,
        headers: dict[str, str] | None = None,
        retry_policy: dict[str, Any] | None = None,
        is_active: bool = True,
    ) -> "WebhookConfig":
        """Create a webhook configuration."""
        from app.core.security import validate_safe_webhook_url
        validate_safe_webhook_url(url)

        webhook = WebhookConfig(
            url=url,
            events=events,
            secret=secret,
            headers=headers,
            retry_policy=retry_policy,
            is_active=is_active,
        )
        self.db.add(webhook)
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def list_webhook_configs(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List webhook configurations."""
        query = select(WebhookConfig)

        # Total count
        count_query = select(func.count()).select_from(select(WebhookConfig).subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = select(WebhookConfig).offset(offset).limit(page_size).order_by(WebhookConfig.created_at.desc())

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_webhook_deliveries(
        self,
        webhook_config_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Get webhook delivery history."""
        query = select(WebhookDelivery).where(WebhookDelivery.webhook_config_id == webhook_config_id)

        # Total count
        count_query = select(func.count()).select_from(
            select(WebhookDelivery).where(WebhookDelivery.webhook_config_id == webhook_config_id).subquery()
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = select(WebhookDelivery).where(
            WebhookDelivery.webhook_config_id == webhook_config_id
        ).offset(offset).limit(page_size).order_by(WebhookDelivery.created_at.desc())

        result = await self.db.execute(query)
        items = result.scalars().all()

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def update_notification_preference(
        self,
        user_id: UUID,
        channel: str,
        event_type: str,
        enabled: bool,
        conditions: dict[str, Any] | None = None,
    ) -> "NotificationPreference":
        """Update user notification preference."""
        result = await self.db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.channel == channel,
                NotificationPreference.event_type == channel,  # Match event_type to channel for now
            )
        )
        pref = result.scalars().first()

        if pref:
            pref.enabled = enabled
            pref.conditions = conditions
            pref.updated_at = datetime.now(UTC)
        else:
            pref = NotificationPreference(
                user_id=user_id,
                channel=channel,
                event_type=channel,
                enabled=enabled,
                conditions=conditions,
            )
            self.db.add(pref)

        await self.db.commit()
        await self.db.refresh(pref)
        return pref

    async def get_notification_stats(self) -> dict[str, Any]:
        """Get notification statistics."""
        total = await self.db.scalar(select(func.count(Notification.id)))
        sent = await self.db.scalar(
            select(func.count(Notification.id)).where(Notification.status == "sent")
        )
        failed = await self.db.scalar(
            select(func.count(Notification.id)).where(Notification.status == "failed")
        )

        # By channel
        channel_result = await self.db.execute(
            select(Notification.channel, func.count(Notification.id)).group_by(Notification.channel)
        )
        by_channel = {row[0]: row[1] for row in channel_result}

        # By status
        status_result = await self.db.execute(
            select(Notification.status, func.count(Notification.id)).group_by(Notification.status)
        )
        by_status = {row[0]: row[1] for row in status_result}

        # By priority
        priority_result = await self.db.execute(
            select(Notification.priority, func.count(Notification.id)).group_by(Notification.priority)
        )
        by_priority = {row[0]: row[1] for row in priority_result}

        total = total or 0
        sent = sent or 0
        failed = failed or 0
        success_rate = (sent / total * 100) if total > 0 else 0

        return {
            "total_sent": total,
            "total_failed": failed,
            "by_channel": by_channel,
            "by_status": by_status,
            "by_priority": by_priority,
            "success_rate": success_rate,
        }

    async def process_scheduled_notifications(self) -> int:
        """Process scheduled notifications that are due."""
        result = await self.db.execute(
            select(Notification).where(
                Notification.status == "pending",
                Notification.scheduled_at.is_not(None),
                Notification.scheduled_at <= datetime.now(UTC),
            )
        )
        notifications = result.scalars().all()

        sent_count = 0
        for notification in notifications:
            success = await self._send_via_channel(notification)
            notification.status = NotificationStatus.SENT if success else NotificationStatus.FAILED
            if success:
                notification.sent_at = datetime.now(UTC)
            else:
                notification.error_message = "Failed to send scheduled notification"
            sent_count += 1

        await self.db.commit()
        return sent_count


def create_notification_service(db: AsyncSession) -> NotificationService:
    """Factory for creating NotificationService."""
    return NotificationService(db)
