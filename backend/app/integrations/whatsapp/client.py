"""WhatsApp Business API client."""

import hashlib
import hmac
from typing import Any, NotRequired
from urllib.parse import urljoin

import httpx
from typing_extensions import TypedDict

from app.core.config import settings
from app.core.logging import get_logger


class TemplateComponents(TypedDict):
    type: str
    parameters: NotRequired[list[dict[str, Any]]]


class MediaPayload(TypedDict):
    id: str
    caption: NotRequired[str]


logger = get_logger(__name__)


class WhatsAppClient:
    """Client for WhatsApp Business Cloud API."""

    def __init__(
        self,
        access_token: str | None = None,
        phone_number_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self.access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN or settings.WHATSAPP_APP_SECRET
        phone_id = (phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID or "").strip("/")
        self.phone_number_id = phone_id
        self.app_secret = app_secret or settings.WHATSAPP_APP_SECRET
        self.base_url = f"https://graph.facebook.com/v20.0/{self.phone_number_id}/" if self.phone_number_id else "https://graph.facebook.com/v20.0/"

    @property
    def messages_url(self) -> str:
        """Endpoint for sending messages, media, templates, and read receipts."""
        return f"https://graph.facebook.com/v20.0/{self.phone_number_id}/messages"

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def send_text_message(self, to: str, body: str) -> dict[str, Any]:
        """Send a text message."""
        url = self.messages_url
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        return await self._post(url, payload)

    async def send_template_message(
        self, to: str, template_name: str, language_code: str = "en", components: list[dict] | None = None
    ) -> dict[str, Any]:
        """Send a template message."""
        url = self.messages_url
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components  # type: ignore[index]
        return await self._post(url, payload)

    async def send_media_message(
        self, to: str, media_type: str, media_id: str, caption: str | None = None
    ) -> dict[str, Any]:
        """Send a media message (image, document, etc.)."""
        url = self.messages_url
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": media_type,
            media_type: {"id": media_id},
        }
        if caption:
            payload[media_type]["caption"] = caption  # type: ignore[index]
        return await self._post(url, payload)

    async def mark_as_read(self, message_id: str) -> dict[str, Any]:
        """Mark a message as read."""
        url = self.messages_url
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        return await self._post(url, payload)

    async def get_media_url(self, media_id: str) -> dict[str, Any]:
        """Get media URL for downloading."""
        url = f"https://graph.facebook.com/v20.0/{media_id}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]

    async def download_media(self, media_url: str) -> bytes:
        """Download media file."""
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(media_url, headers=self._get_headers())
            response.raise_for_status()
            return response.content

    async def _post(self, url: str, payload: dict) -> dict[str, Any]:
        """Make POST request to WhatsApp API."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]


class WhatsAppWebhookVerifier:
    """Verifies WhatsApp webhook signatures."""

    def __init__(self, app_secret: str | None = None) -> None:
        self.app_secret = app_secret or settings.WHATSAPP_APP_SECRET

    def verify_signature(self, payload: bytes, signature_header: str) -> bool:
        """Verify X-Hub-Signature-256 header."""
        if not signature_header or not signature_header.startswith("sha256="):
            return False

        expected_signature = hmac.new(
            self.app_secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        provided_signature = signature_header[7:]  # Remove "sha256="
        return hmac.compare_digest(expected_signature, provided_signature)

    def verify_webhook_challenge(
        self, mode: str, token: str, challenge: str
    ) -> str | None:
        """Verify webhook subscription challenge."""
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            return challenge
        return None


def parse_whatsapp_webhook(payload: dict) -> list[dict]:
    """Parse WhatsApp webhook payload into normalized messages."""
    messages = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            if change.get("field") == "messages":
                for message in value.get("messages", []):
                    messages.append(_normalize_message(message, value.get("contacts", [])))

            elif change.get("field") == "statuses":
                for status in value.get("statuses", []):
                    messages.append(_normalize_status(status))

    return messages


def _normalize_message(message: dict, contacts: list[dict]) -> dict:
    """Normalize incoming message."""
    contact_map = {c.get("wa_id"): c for c in contacts}
    contact = contact_map.get(message.get("from"), {})

    normalized = {
        "id": message.get("id"),
        "from": message.get("from"),
        "timestamp": message.get("timestamp"),
        "type": message.get("type"),
        "contact_name": contact.get("profile", {}).get("name"),
    }

    msg_type = message.get("type")

    if msg_type == "text":
        normalized["text"] = message.get("text", {}).get("body")
    elif msg_type in ("image", "document", "audio", "video", "sticker"):
        media = message.get(msg_type, {})
        normalized["media_id"] = media.get("id")
        normalized["mime_type"] = media.get("mime_type")
        normalized["caption"] = media.get("caption")
        normalized["filename"] = media.get("filename")
    elif msg_type == "location":
        loc = message.get("location", {})
        normalized["latitude"] = loc.get("latitude")
        normalized["longitude"] = loc.get("longitude")
        normalized["name"] = loc.get("name")
        normalized["address"] = loc.get("address")
    elif msg_type == "contacts":
        normalized["contacts"] = message.get("contacts")
    elif msg_type == "interactive":
        normalized["interactive"] = message.get("interactive")

    return normalized


def _normalize_status(status: dict) -> dict:
    """Normalize status update."""
    return {
        "id": status.get("id"),
        "status": status.get("status"),
        "timestamp": status.get("timestamp"),
        "recipient_id": status.get("recipient_id"),
        "conversation": status.get("conversation"),
        "pricing": status.get("pricing"),
        "errors": status.get("errors"),
    }


def create_whatsapp_client() -> WhatsAppClient:
    """Factory for creating WhatsAppClient."""
    return WhatsAppClient()


def create_webhook_verifier() -> WhatsAppWebhookVerifier:
    """Factory for creating WhatsAppWebhookVerifier."""
    return WhatsAppWebhookVerifier()
