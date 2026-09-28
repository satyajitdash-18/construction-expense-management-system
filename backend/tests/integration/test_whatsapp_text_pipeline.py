"""End-to-end integration test for WhatsApp text message -> LLM extraction -> Expense creation -> Audit trail."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus, JobType, LifecycleStatus, SourceType
from app.models.expense import Expense
from app.models.processing_job import ProcessingJob
from app.models.project import Project, ProjectStatus
from app.models.source_event import SourceEvent
from app.models.audit_event import AuditEvent
from app.services.llm_extraction import ExtractionResult
from app.services.whatsapp import WhatsAppService
from app.tasks.llm_extraction import _process_llm_extraction_async


class DummyTask:
    request = None
    max_retries = 2


@pytest.mark.asyncio
async def test_whatsapp_text_to_expense_e2e_pipeline(db_session: AsyncSession, test_user):
    """Test full pipeline: WhatsApp text -> SourceEvent -> LLM extraction -> Expense staging -> Audit log."""
    # 1. Setup active project
    project = Project(
        name="Pipeline Test Site",
        code=f"PIPE-{uuid.uuid4().hex[:8]}",
        created_by=test_user.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(project)
    await db_session.commit()
    project_id = project.id

    # 2. Mock Celery delay so task doesn't run in real background worker
    with patch("app.tasks.llm_extraction.process_llm_extraction_task.delay") as mock_delay:
        service = WhatsAppService(db_session)

        msg_id = f"wamid.text_pipeline_{uuid.uuid4().hex[:8]}"
        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messages": [
                                    {
                                        "id": msg_id,
                                        "from": "919988776655",
                                        "type": "text",
                                        "text": {"body": "Bought UltraTech Cement Rs 18500 cash GSTIN 29ABCDE1234F1Z5"},
                                        "timestamp": "1710000000",
                                        "project_id": str(project.id),
                                    }
                                ]
                            },
                        }
                    ]
                }
            ]
        }

        # Process webhook
        await service.process_webhook(webhook_payload)

        # Verify Celery task was scheduled
        mock_delay.assert_called_once()
        queued_job_id = mock_delay.call_args[0][0]

    # 3. Verify SourceEvent was created
    se_res = await db_session.execute(
        select(SourceEvent).where(SourceEvent.external_id == msg_id)
    )
    source_event = se_res.scalars().first()
    assert source_event is not None
    assert source_event.source == SourceType.WHATSAPP
    assert source_event.raw_payload["text"] == "Bought UltraTech Cement Rs 18500 cash GSTIN 29ABCDE1234F1Z5"
    source_event_id = source_event.id

    # 4. Verify ProcessingJob was created
    job = await db_session.get(ProcessingJob, queued_job_id)
    assert job is not None
    assert job.job_type == JobType.LLM_EXTRACT
    assert job.status == JobStatus.PENDING

    # 5. Execute _process_llm_extraction_async with mocked LLM service
    mock_extraction_result = ExtractionResult(
        vendor_name="UltraTech Cement Ltd",
        vendor_gstin="29ABCDE1234F1Z5",
        transaction_date="2026-09-28",
        total_amount=18500.0,
        subtotal=18500.0,
        tax_amount=0.0,
        currency="INR",
        payment_method="CASH",
        confidence_score=0.95,
    )

    with patch("app.tasks.llm_extraction.create_llm_extraction_service") as mock_create_svc:
        mock_svc = MagicMock()
        mock_svc.extract_expense = AsyncMock(return_value=mock_extraction_result)
        mock_create_svc.return_value = mock_svc

        result = await _process_llm_extraction_async(DummyTask(), queued_job_id, None)

    assert result["status"] == "success"

    # 6. Verify Expense was created, staged, and linked
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as verify_db:
        exp_res = await verify_db.execute(
            select(Expense).where(Expense.source_event_id == source_event_id)
        )
        expense = exp_res.scalars().first()
        assert expense is not None
        assert expense.project_id == project_id
        assert expense.total == Decimal("18500.00")
        assert expense.gstin_supplier == "29ABCDE1234F1Z5"
        assert expense.lifecycle_status == LifecycleStatus.STAGED
        assert expense.confidence_score == Decimal("0.95")

        # 7. Verify audit event was logged
        audit_res = await verify_db.execute(
            select(AuditEvent).where(
                AuditEvent.entity_type == "expense",
                AuditEvent.entity_id == expense.id,
                AuditEvent.event_type == "expense.created_from_text",
            )
        )
        audit_event = audit_res.scalars().first()
        assert audit_event is not None
        assert audit_event.payload["source"] == "whatsapp_text"
        assert audit_event.payload["vendor_name"] == "UltraTech Cement Ltd"
