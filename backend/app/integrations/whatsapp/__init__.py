"""WhatsApp Business API integration."""

from enum import Enum


class WhatsAppMessageType(str, Enum):
    """WhatsApp message types."""
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    LOCATION = "location"
    CONTACTS = "contacts"


class WhatsAppWebhookEventType(str, Enum):
    """WhatsApp webhook event types."""
    MESSAGES = "messages"
    STATUS = "status"


WHATSAPP_API_VERSION = "v20.0"
WHATSAPP_BASE_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
