"""WhatsApp service for processing incoming messages and media."""

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.helper import write_audit_event
from app.core.logging import get_logger
from app.integrations.whatsapp.client import create_whatsapp_client, parse_whatsapp_webhook
from app.models.enums import JobStatus, JobType, SourceType
from app.models.evidence import Evidence
from app.models.processing_job import JobAttempt, ProcessingJob
from app.models.source_event import SourceEvent
from app.services.storage import create_storage_service

logger = get_logger(__name__)


class WhatsAppService:
    """Service for handling WhatsApp Business API integration."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.client = create_whatsapp_client()
        self.storage = create_storage_service()

    async def process_webhook(self, payload: dict[str, Any]) -> None:
        """Process incoming WhatsApp webhook payload."""
        messages = parse_whatsapp_webhook(payload)

        for message in messages:
            if message.get("type") in ("image", "document"):
                await self._handle_media_message(message)
            elif message.get("type") == "text":
                await self._handle_text_message(message)
            # Status updates are logged but don't create expenses
            elif message.get("status"):
                logger.info("WhatsApp status update", message=message)

    async def _handle_media_message(self, message: dict[str, Any]) -> None:
        """Handle incoming image/document message."""
        from_number = message.get("from")
        media_id = message.get("media_id")
        mime_type = message.get("mime_type")
        caption = message.get("caption")
        filename = message.get("filename") or f"whatsapp_{media_id}"

        if not from_number or not media_id:
            logger.warning("Incomplete media message", message=message)
            return

        logger.info(
            "Processing WhatsApp media",
            from_number=from_number,
            media_id=media_id,
            mime_type=mime_type,
        )

        # Get media URL from WhatsApp
        media_info = await self.client.get_media_url(media_id)
        media_url = media_info.get("url")
        if not media_url:
            logger.error("No media URL returned", media_id=media_id)
            return

        # Download media
        file_data = await self.client.download_media(media_url)

        # Compute checksum
        checksum = hashlib.sha256(file_data).hexdigest()

        # Create idempotency key from WhatsApp message ID
        idempotency_key = f"whatsapp_{message.get('id')}"

        # Check if already processed
        existing = await self.db.execute(
            select(SourceEvent).where(SourceEvent.idempotency_key == idempotency_key)
        )
        if existing.scalar_one_or_none():
            logger.info("Duplicate WhatsApp message ignored", idempotency_key=idempotency_key)
            return

        # Create source event
        source_event = SourceEvent(
            source=SourceType.WHATSAPP,
            external_id=message.get("id"),
            idempotency_key=idempotency_key,
            raw_payload={
                "from": from_number,
                "media_id": media_id,
                "mime_type": mime_type,
                "caption": caption,
                "timestamp": message.get("timestamp"),
            },
        )
        self.db.add(source_event)
        await self.db.flush()

        # Write audit event
        await write_audit_event(
            session=self.db,
            event_type="source_event.created",
            entity_type="source_event",
            entity_id=source_event.id,
            actor_id=None,
            payload={
                "source": "whatsapp",
                "from": from_number,
                "media_id": media_id,
            },
        )

        # Upload to MinIO
        object_name = f"whatsapp/{source_event.id}/{filename}"
        _, stored_checksum = self.storage.upload_file(
            object_name=object_name,
            data=file_data,
            content_type=mime_type,
            metadata={"source": "whatsapp", "from": from_number},
        )

        # Verify checksum
        if stored_checksum != checksum:
            logger.error("Checksum mismatch after upload", expected=checksum, got=stored_checksum)

        # Create evidence record
        evidence = Evidence(
            expense_id=None,  # Will be linked after expense creation
            object_name=object_name,
            file_name=filename,
            content_type=mime_type or "application/octet-stream",
            size=len(file_data),
            checksum=stored_checksum,
            file_metadata={
                "source": "whatsapp",
                "from": from_number,
                "caption": caption,
                "timestamp": message.get("timestamp"),
            },
        )
        self.db.add(evidence)
        await self.db.flush()

        # Create processing job for OCR
        ocr_job = ProcessingJob(
            job_type=JobType.OCR,
            source_event_id=source_event.id,
            status=JobStatus.PENDING,
        )
        self.db.add(ocr_job)
        await self.db.flush()

        # Create job attempt
        attempt = JobAttempt(
            processing_job_id=ocr_job.id,
            attempt_number=1,
        )
        self.db.add(attempt)
        await self.db.commit()

        # Queue OCR task
        from app.tasks.ocr import process_ocr_task
        process_ocr_task.delay(str(ocr_job.id), str(evidence.id))

        logger.info(
            "WhatsApp media queued for OCR",
            source_event_id=str(source_event.id),
            evidence_id=str(evidence.id),
            ocr_job_id=str(ocr_job.id),
        )

    async def _handle_text_message(self, message: dict[str, Any]) -> None:
        """Handle incoming text message (could be expense data in text form)."""
        from_number = message.get("from")
        text = message.get("text")
        message_id = message.get("id")

        if not from_number or not text:
            return

        logger.info("Processing WhatsApp text", from_number=from_number, text=text[:100])

        idempotency_key = f"whatsapp_{message_id}"

        # Check if already processed
        existing = await self.db.execute(
            select(SourceEvent).where(SourceEvent.idempotency_key == idempotency_key)
        )
        if existing.scalar_one_or_none():
            logger.info("Duplicate WhatsApp text ignored", idempotency_key=idempotency_key)
            return

        # Create source event for text
        source_event = SourceEvent(
            source=SourceType.WHATSAPP,
            external_id=message_id,
            idempotency_key=idempotency_key,
            raw_payload={
                "from": from_number,
                "text": text,
                "timestamp": message.get("timestamp"),
            },
        )
        self.db.add(source_event)
        await self.db.flush()

        # Write audit event
        await write_audit_event(
            session=self.db,
            event_type="source_event.created",
            entity_type="source_event",
            entity_id=source_event.id,
            actor_id=None,
            payload={"source": "whatsapp", "from": from_number, "type": "text"},
        )

        # Create processing job for LLM extraction directly (text doesn't need OCR)
        extract_job = ProcessingJob(
            job_type=JobType.LLM_EXTRACT,
            source_event_id=source_event.id,
            status=JobStatus.PENDING,
        )
        self.db.add(extract_job)
        await self.db.flush()

        # Create attempt
        attempt = JobAttempt(
            processing_job_id=extract_job.id,
            attempt_number=1,
        )
        self.db.add(attempt)
        await self.db.commit()

        # Queue LLM extraction
        from app.tasks.llm_extraction import process_llm_extraction_task
        process_llm_extraction_task.delay(str(extract_job.id), None)

        logger.info("WhatsApp text queued for extraction", source_event_id=str(source_event.id))

    async def send_confirmation(self, to: str, expense_id: UUID, status: str) -> None:
        """Send confirmation message for processed expense."""
        if status == "staged":
            body = f"✅ Expense recorded successfully (ID: {str(expense_id)[:8]})."
        elif status == "needs_confirmation":
            body = f"⚠️ Expense needs review (ID: {str(expense_id)[:8]}). Please check the app."
        else:
            body = f"ℹ️ Expense update: {status}"

        await self.client.send_text_message(to, body)

    async def send_error(self, to: str, error: str) -> None:
        """Send error message."""
        body = f"❌ Error processing expense: {error}"
        await self.client.send_text_message(to, body)


def create_whatsapp_service(db: AsyncSession) -> WhatsAppService:
    """Factory for creating WhatsAppService."""
    return WhatsAppService(db)
