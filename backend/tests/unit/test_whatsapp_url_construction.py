"""Unit tests for WhatsApp Business API client URL construction."""

from unittest.mock import AsyncMock, patch
from urllib.parse import urljoin
import pytest

from app.integrations.whatsapp.client import WhatsAppClient


@pytest.fixture
def whatsapp_client():
    return WhatsAppClient(
        access_token="test_access_token_123",
        phone_number_id="109876543210",
        app_secret="test_app_secret_xyz",
    )


def test_whatsapp_base_url_and_messages_url(whatsapp_client: WhatsAppClient):
    """Verify messages_url and base_url retain the phone_number_id."""
    phone_id = "109876543210"
    expected_messages_url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"

    assert whatsapp_client.phone_number_id == phone_id
    assert whatsapp_client.messages_url == expected_messages_url
    assert urljoin(whatsapp_client.base_url, "messages") == expected_messages_url


@pytest.mark.asyncio
async def test_send_text_message_target_url(whatsapp_client: WhatsAppClient):
    """Verify send_text_message dispatches to the correct phone-specific messages URL."""
    expected_url = f"https://graph.facebook.com/v20.0/{whatsapp_client.phone_number_id}/messages"

    with patch.object(whatsapp_client, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"messages": [{"id": "wamid.test"}]}
        res = await whatsapp_client.send_text_message(to="919876543210", body="Test expense")

        mock_post.assert_awaited_once()
        called_url, called_payload = mock_post.await_args.args
        assert called_url == expected_url
        assert called_payload["to"] == "919876543210"
        assert called_payload["type"] == "text"


@pytest.mark.asyncio
async def test_send_template_message_target_url(whatsapp_client: WhatsAppClient):
    """Verify send_template_message dispatches to the correct phone-specific messages URL."""
    expected_url = f"https://graph.facebook.com/v20.0/{whatsapp_client.phone_number_id}/messages"

    with patch.object(whatsapp_client, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"messages": [{"id": "wamid.template"}]}
        res = await whatsapp_client.send_template_message(to="919876543210", template_name="expense_alert")

        mock_post.assert_awaited_once()
        called_url, called_payload = mock_post.await_args.args
        assert called_url == expected_url
        assert called_payload["type"] == "template"


@pytest.mark.asyncio
async def test_send_media_message_target_url(whatsapp_client: WhatsAppClient):
    """Verify send_media_message dispatches to the correct phone-specific messages URL."""
    expected_url = f"https://graph.facebook.com/v20.0/{whatsapp_client.phone_number_id}/messages"

    with patch.object(whatsapp_client, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"messages": [{"id": "wamid.media"}]}
        res = await whatsapp_client.send_media_message(
            to="919876543210", media_type="image", media_id="media_999", caption="Receipt"
        )

        mock_post.assert_awaited_once()
        called_url, called_payload = mock_post.await_args.args
        assert called_url == expected_url
        assert called_payload["type"] == "image"


@pytest.mark.asyncio
async def test_mark_as_read_target_url(whatsapp_client: WhatsAppClient):
    """Verify mark_as_read dispatches to the correct phone-specific messages URL."""
    expected_url = f"https://graph.facebook.com/v20.0/{whatsapp_client.phone_number_id}/messages"

    with patch.object(whatsapp_client, "_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"success": True}
        res = await whatsapp_client.mark_as_read(message_id="wamid.msg123")

        mock_post.assert_awaited_once()
        called_url, called_payload = mock_post.await_args.args
        assert called_url == expected_url
        assert called_payload["status"] == "read"
