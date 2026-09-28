"""Unit tests for notification provider architecture and channel delivery."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationChannel, NotificationStatus
from app.models.notification import Notification
from app.services.notification import (
    BaseNotificationProvider,
    EmailNotificationProvider,
    NotificationService,
    PushNotificationProvider,
    SMSNotificationProvider,
    WhatsAppNotificationProvider,
)


class MockSuccessProvider(BaseNotificationProvider):
    def is_configured(self) -> bool:
        return True

    async def send(self, notification: Notification) -> tuple[bool, str | None]:
        return True, None


@pytest.mark.asyncio
async def test_notification_provider_unconfigured_failure(db_session: AsyncSession):
    """Test that unconfigured notification channels fail explicitly with informative error."""
    # Ensure unconfigured
    with patch("app.services.notification.settings") as mock_settings:
        mock_settings.SMTP_HOST = ""
        mock_settings.TWILIO_ACCOUNT_SID = ""
        mock_settings.TWILIO_AUTH_TOKEN = ""
        mock_settings.WHATSAPP_ACCESS_TOKEN = ""
        mock_settings.WHATSAPP_PHONE_NUMBER_ID = ""
        mock_settings.FCM_SERVER_KEY = ""

        service = NotificationService(
            db_session,
            providers={
                "email": EmailNotificationProvider(host=""),
                "sms": SMSNotificationProvider(account_sid="", auth_token=""),
                "whatsapp": WhatsAppNotificationProvider(access_token="", phone_number_id=""),
                "push": PushNotificationProvider(server_key=""),
            },
        )

        # Test Email
        nid_email = await service.send_notification(
            channel="email",
            subject="Test Subject",
            body="Test body",
        )
        notif_email = await db_session.get(Notification, nid_email)
        assert notif_email is not None
        assert notif_email.status == NotificationStatus.FAILED
        assert "Provider not configured: email" in (notif_email.error_message or "")

        # Test SMS
        nid_sms = await service.send_notification(
            channel="sms",
            subject=None,
            body="SMS body",
        )
        notif_sms = await db_session.get(Notification, nid_sms)
        assert notif_sms is not None
        assert notif_sms.status == NotificationStatus.FAILED
        assert "Provider not configured: sms" in (notif_sms.error_message or "")

        # Test WhatsApp
        nid_wa = await service.send_notification(
            channel="whatsapp",
            subject=None,
            body="WA body",
            metadata={"recipient_phone": "+1234567890"},
        )
        notif_wa = await db_session.get(Notification, nid_wa)
        assert notif_wa is not None
        assert notif_wa.status == NotificationStatus.FAILED
        assert "Provider not configured: whatsapp" in (notif_wa.error_message or "")


@pytest.mark.asyncio
async def test_notification_provider_configured_success(db_session: AsyncSession):
    """Test that configured providers mark status as SENT and record sent_at timestamp."""
    service = NotificationService(db_session)
    # Register mock configured provider
    service.register_provider("email", MockSuccessProvider())

    nid = await service.send_notification(
        channel="email",
        subject="Invoice Alert",
        body="Invoice approved",
    )
    notif = await db_session.get(Notification, nid)
    assert notif is not None
    assert notif.status == NotificationStatus.SENT
    assert notif.sent_at is not None
    assert notif.error_message is None


@pytest.mark.asyncio
async def test_whatsapp_provider_delegation_to_client(db_session: AsyncSession):
    """Test WhatsApp provider invokes WhatsAppClient with recipient and body."""
    mock_client_instance = AsyncMock()
    mock_client_instance.send_text_message.return_value = {"messages": [{"id": "wamid.123"}]}

    with patch("app.integrations.whatsapp.client.WhatsAppClient", return_value=mock_client_instance):
        provider = WhatsAppNotificationProvider(
            access_token="valid_token",
            phone_number_id="123456789",
        )
        assert provider.is_configured() is True

        service = NotificationService(db_session)
        service.register_provider("whatsapp", provider)

        # Success case with recipient in metadata
        nid = await service.send_notification(
            channel="whatsapp",
            subject=None,
            body="Your expense of $450 has been recorded.",
            metadata={"recipient_phone": "+919876543210"},
        )
        notif = await db_session.get(Notification, nid)
        assert notif is not None
        assert notif.status == NotificationStatus.SENT
        mock_client_instance.send_text_message.assert_awaited_once_with(
            to="+919876543210",
            text="Your expense of $450 has been recorded.",
        )


@pytest.mark.asyncio
async def test_whatsapp_provider_missing_recipient(db_session: AsyncSession):
    """Test WhatsApp provider fails gracefully when recipient phone number is missing."""
    provider = WhatsAppNotificationProvider(
        access_token="valid_token",
        phone_number_id="123456789",
    )
    service = NotificationService(db_session)
    service.register_provider("whatsapp", provider)

    nid = await service.send_notification(
        channel="whatsapp",
        subject=None,
        body="Message without recipient",
        metadata={},  # No phone number
    )
    notif = await db_session.get(Notification, nid)
    assert notif is not None
    assert notif.status == NotificationStatus.FAILED
    assert "Recipient phone number not specified" in (notif.error_message or "")


@pytest.mark.asyncio
async def test_update_notification_preference_distinguishes_event_type(
    db_session: AsyncSession,
    test_user,
):
    """Test that update_notification_preference creates distinct preferences per event_type."""
    from app.models.notification import NotificationPreference

    service = NotificationService(db_session)
    user_id = test_user.id

    # Create preference for expense_approved
    pref1 = await service.update_notification_preference(
        user_id=user_id,
        channel="email",
        event_type="expense_approved",
        enabled=True,
    )
    assert pref1.user_id == user_id
    assert pref1.channel == "email"
    assert pref1.event_type == "expense_approved"
    assert pref1.enabled is True

    # Create preference for budget_exceeded on same channel
    pref2 = await service.update_notification_preference(
        user_id=user_id,
        channel="email",
        event_type="budget_exceeded",
        enabled=False,
    )
    assert pref2.id != pref1.id
    assert pref2.event_type == "budget_exceeded"
    assert pref2.enabled is False

    # Update existing preference for expense_approved
    pref1_updated = await service.update_notification_preference(
        user_id=user_id,
        channel="email",
        event_type="expense_approved",
        enabled=False,
    )
    assert pref1_updated.id == pref1.id
    assert pref1_updated.enabled is False


@pytest.mark.asyncio
async def test_process_scheduled_notifications_counts_only_successes(
    db_session: AsyncSession,
    test_user,
):
    """Test that process_scheduled_notifications returns accurate count of succeeded sends only."""
    from datetime import datetime, timedelta, UTC

    # Create one notification with configured email and one with unconfigured push
    service = NotificationService(db_session)
    service.register_provider("email", MockSuccessProvider())
    # push is unconfigured by default, will fail

    n_success = Notification(
        user_id=test_user.id,
        channel="email",
        status=NotificationStatus.PENDING,
        subject="Scheduled Success",
        body="Body 1",
        scheduled_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    n_fail = Notification(
        user_id=test_user.id,
        channel="push",
        status=NotificationStatus.PENDING,
        subject="Scheduled Failure",
        body="Body 2",
        scheduled_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.add_all([n_success, n_fail])
    await db_session.commit()

    sent_count = await service.process_scheduled_notifications()
    assert sent_count == 1

    await db_session.refresh(n_success)
    await db_session.refresh(n_fail)
    assert n_success.status == NotificationStatus.SENT
    assert n_fail.status == NotificationStatus.FAILED

