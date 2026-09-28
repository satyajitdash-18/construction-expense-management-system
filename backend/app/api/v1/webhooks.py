"""WhatsApp webhook API endpoints."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.integrations.whatsapp.client import (
    WhatsAppWebhookVerifier,
    create_webhook_verifier,
)
from app.services.whatsapp import create_whatsapp_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

logger = get_logger(__name__)


@router.get("/whatsapp")
async def whatsapp_webhook_verification(
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
    verifier: WhatsAppWebhookVerifier = Depends(create_webhook_verifier),
) -> str:
    """
    WhatsApp webhook verification endpoint.

    Meta sends a GET request with hub.mode, hub.verify_token, and hub.challenge.
    We must respond with the challenge if verification succeeds.
    """
    result = verifier.verify_webhook_challenge(
        mode=mode or "", token=token or "", challenge=challenge or ""
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid verification token",
        )

    return result


@router.post("/whatsapp")
async def whatsapp_webhook_receive(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    verifier: WhatsAppWebhookVerifier = Depends(create_webhook_verifier),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Receive WhatsApp webhook events.

    Handles incoming messages and status updates.
    """
    payload = await request.body()

    # Verify signature
    if not verifier.verify_signature(payload, x_hub_signature_256 or ""):
        logger.warning("Invalid WhatsApp webhook signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )

    # Parse JSON
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON",
        ) from err

    # Process webhook asynchronously
    service = create_whatsapp_service(db)
    await service.process_webhook(data)

    return {"status": "ok"}
