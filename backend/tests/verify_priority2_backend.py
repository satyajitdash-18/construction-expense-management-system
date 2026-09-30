"""Targeted verification test suite for Priority 2 Core Backend & Financial Integrity Fixes."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock optional dependencies when running in standalone host test environment
if "minio" not in sys.modules:
    sys.modules["minio"] = MagicMock()
if "minio.error" not in sys.modules:
    sys.modules["minio.error"] = MagicMock()
if "sentry_sdk" not in sys.modules:
    sys.modules["sentry_sdk"] = MagicMock()

import pytest


# ---------------------------------------------------------------------------
# Test 1: Celery Worker Boot Entrypoint in Docker Compose
# ---------------------------------------------------------------------------
def test_celery_worker_entrypoint():
    print("[1/12] Testing Celery Worker Entrypoint in docker-compose.yml...")
    compose_path = Path(__file__).parent.parent.parent / "infrastructure" / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"

    content = compose_path.read_text(encoding="utf-8")
    assert "celery -A app.core.celery_app worker" in content, (
        "docker-compose.yml celery worker entrypoint must point to app.core.celery_app"
    )
    assert "celery -A app.workers.celery_app" not in content, (
        "Non-existent app.workers.celery_app entrypoint still present"
    )
    print("  -> PASSED: Worker entrypoint correctly points to app.core.celery_app")


# ---------------------------------------------------------------------------
# Test 2: Valid Celery Task Modules & Beat Schedule
# ---------------------------------------------------------------------------
def test_celery_task_modules():
    print("[2/12] Testing Celery Task Modules and Beat Schedule...")
    from app.core.celery_app import celery_app
    from app.core.celery_beat_schedule import CELERY_BEAT_SCHEDULE

    # Check included modules
    includes = celery_app.conf.include
    invalid_modules = [
        "app.tasks.extraction",
        "app.tasks.reconciliation",
        "app.tasks.notifications",
        "app.tasks.audit",
        "app.tasks.budget",
        "app.tasks.monitoring",
        "app.tasks.search",
    ]
    for inv in invalid_modules:
        assert inv not in includes, f"Invalid task module {inv} should not be in celery_app includes"

    assert "app.tasks.ocr" in includes, "app.tasks.ocr must be in celery includes"
    assert "app.tasks.llm_extraction" in includes, "app.tasks.llm_extraction must be in celery includes"
    assert "app.tasks.maintenance" in includes, "app.tasks.maintenance must be in celery includes"

    # Verify all tasks in beat schedule reference app.tasks.maintenance
    for name, config in CELERY_BEAT_SCHEDULE.items():
        task_name = config["task"]
        assert task_name.startswith("app.tasks.maintenance."), (
            f"Beat schedule task {task_name} must point to a real maintenance task"
        )

    print("  -> PASSED: Celery tasks include only existing modules and valid beat schedules")


# ---------------------------------------------------------------------------
# Test 3 & 4: OCR -> LLM Linkage & Worker Job ID Handling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ocr_llm_job_linkage_and_handling():
    print("[3 & 4/12] Testing OCR -> LLM Job Linkage and Passed Job ID Handling...")
    from app.models.enums import JobStatus, JobType
    from app.models.expense import Expense
    from app.models.processing_job import ProcessingJob

    # 1. Inspect OCR worker task logic
    from app.tasks.ocr import process_ocr_task
    assert hasattr(process_ocr_task, "delay"), "process_ocr_task must be a Celery task"

    # 2. Inspect LLM extraction task logic
    from app.tasks.llm_extraction import process_llm_extraction_task
    assert hasattr(process_llm_extraction_task, "delay"), "process_llm_extraction_task must be a Celery task"

    # Verify OCR endpoint passes source_event_id to ProcessingJob
    ocr_file = (Path(__file__).parent.parent / "app" / "api" / "v1" / "ocr.py").read_text(encoding="utf-8")
    assert "source_event_id=source_event_id" in ocr_file, (
        "OCR API must link ProcessingJob.source_event_id with expense.source_event_id"
    )

    # Verify LLM extraction worker queries OCR job by source_event_id
    llm_worker_file = (Path(__file__).parent.parent / "app" / "tasks" / "llm_extraction.py").read_text(encoding="utf-8")
    assert "ProcessingJob.source_event_id == job.source_event_id" in llm_worker_file, (
        "LLM extraction worker must correlate OCR job using source_event_id"
    )
    print("  -> PASSED: ProcessingJob.source_event_id linkage and worker job handling verified")


# ---------------------------------------------------------------------------
# Test 5: Expense Update Endpoint Actually Persists Permitted Fields
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_expense_update_persistence():
    print("[5/12] Testing Expense PATCH/Update Persistence...")
    from app.models.expense import Expense
    from app.models.enums import LifecycleStatus, PaymentMethod
    from app.schemas.expense import ExpenseUpdate
    from app.services.expense import ExpenseService

    expense_id = uuid4()
    mock_expense = Expense(
        id=expense_id,
        project_id=uuid4(),
        source_event_id=uuid4(),
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
        total=Decimal("118.00"),
        currency="INR",
        lifecycle_status=LifecycleStatus.RECEIVED,
        payment_method=PaymentMethod.CASH,
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    service = ExpenseService(mock_db)
    service.repo.get_by_id = AsyncMock(return_value=mock_expense)

    new_vendor_id = uuid4()
    new_category_id = uuid4()
    update_data = ExpenseUpdate(
        subtotal=Decimal("200.00"),
        tax_amount=Decimal("36.00"),
        total=Decimal("236.00"),
        vendor_id=new_vendor_id,
        category_id=new_category_id,
        payment_method=PaymentMethod.UPI,
    )

    user_id = uuid4()
    updated = await service.update_expense(
        expense_id=expense_id,
        update_data=update_data.model_dump(exclude_unset=True),
        actor_id=user_id,
    )

    assert updated.total == Decimal("236.00"), "total was not updated"
    assert updated.vendor_id == new_vendor_id, "vendor_id was not updated"
    assert updated.category_id == new_category_id, "category_id was not updated"
    assert updated.payment_method == PaymentMethod.UPI, "payment_method was not updated"
    assert mock_db.commit.called or mock_db.flush.called, "Database commit/flush was not called"
    print("  -> PASSED: Expense update persists permitted fields and commits")


# ---------------------------------------------------------------------------
# Test 6: Manual Expense Category Assignment
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manual_expense_category_persistence():
    print("[6/12] Testing Manual Expense Category Assignment...")
    from app.services.expense import ExpenseService

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    service = ExpenseService(mock_db)
    category_id = uuid4()

    created = await service.create_manual_expense(
        project_id=uuid4(),
        created_by=uuid4(),
        transaction_date="2026-09-20",
        subtotal=500.00,
        tax_amount=0.00,
        total=500.00,
        currency="INR",
        payment_method="CASH",
        category_id=category_id,
    )

    assert created.category_id == category_id, (
        f"Expected category_id {category_id}, got {created.category_id}"
    )
    print("  -> PASSED: Manual expense creation correctly assigns category_id")


# ---------------------------------------------------------------------------
# Test 7: Transaction / Celery Race Condition (Commit Before Delay)
# ---------------------------------------------------------------------------
def test_celery_dispatch_after_commit():
    print("[7/12] Testing Commit Before Celery Task Dispatch...")
    ocr_api_content = (Path(__file__).parent.parent / "app" / "api" / "v1" / "ocr.py").read_text(encoding="utf-8")
    extract_api_content = (Path(__file__).parent.parent / "app" / "api" / "v1" / "extraction.py").read_text(encoding="utf-8")

    # In ocr.py, commit() must appear before .delay()
    ocr_commit_idx = ocr_api_content.find("await db.commit()")
    ocr_delay_idx = ocr_api_content.find("process_ocr_task.delay")
    assert ocr_commit_idx != -1 and ocr_delay_idx != -1, "ocr.py must contain commit() and .delay()"
    assert ocr_commit_idx < ocr_delay_idx, "ocr.py must commit to DB before dispatching Celery task"

    # In extraction.py, commit() must appear before .delay()
    ext_commit_idx = extract_api_content.find("await db.commit()")
    ext_delay_idx = extract_api_content.find("process_llm_extraction_task.delay")
    assert ext_commit_idx != -1 and ext_delay_idx != -1, "extraction.py must contain commit() and .delay()"
    assert ext_commit_idx < ext_delay_idx, "extraction.py must commit to DB before dispatching Celery task"

    print("  -> PASSED: DB transactions commit before Celery task dispatch")


# ---------------------------------------------------------------------------
# Test 8: WhatsApp Cloud API Authentication
# ---------------------------------------------------------------------------
def test_whatsapp_auth_token_usage():
    print("[8/12] Testing WhatsApp Authentication Token Usage...")
    from app.integrations.whatsapp.client import WhatsAppClient

    client = WhatsAppClient(
        phone_number_id="123456",
        access_token="SYSTEM_USER_ACCESS_TOKEN_ABC",
        app_secret="APP_SECRET_XYZ",
    )

    # Verify authorization header uses access_token
    auth_header = client._get_headers().get("Authorization")
    assert auth_header == "Bearer SYSTEM_USER_ACCESS_TOKEN_ABC", (
        f"Expected Bearer access_token, got {auth_header}"
    )

    # Verify app_secret is stored separately for webhook verification and not exposed in headers
    assert client.app_secret == "APP_SECRET_XYZ"
    assert "APP_SECRET_XYZ" not in auth_header

    print("  -> PASSED: WhatsApp client uses system-user access token for Bearer auth")


# ---------------------------------------------------------------------------
# Test 9: Ledger Posting Flush Order (source_audit_event_id Non-Null FK)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ledger_posting_audit_event_flush_order():
    print("[9/12] Testing Ledger Posting Audit Event Flush Order...")
    from app.services.posting import PostingService
    from app.models.expense import Expense
    from app.models.enums import AccountType, LifecycleStatus
    from app.models.ledger import LedgerAccount

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    service = PostingService(mock_db)
    service.get_default_accounts = AsyncMock(return_value={
        AccountType.EXPENSE: LedgerAccount(id=uuid4(), name="Expenses", account_type=AccountType.EXPENSE),
        AccountType.ASSET: LedgerAccount(id=uuid4(), name="Cash", account_type=AccountType.ASSET),
        AccountType.LIABILITY: LedgerAccount(id=uuid4(), name="Payable", account_type=AccountType.LIABILITY),
    })
    service._get_or_create_tax_account = AsyncMock(
        return_value=LedgerAccount(id=uuid4(), name="Tax", account_type=AccountType.ASSET)
    )

    # Create mock expense in RECONCILED status
    expense = Expense(
        id=uuid4(),
        project_id=uuid4(),
        source_event_id=uuid4(),
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("180.00"),
        total=Decimal("1180.00"),
        currency="INR",
        lifecycle_status=LifecycleStatus.RECONCILED,
        cgst_amount=Decimal("90.00"),
        sgst_amount=Decimal("90.00"),
    )
    mock_db.get.return_value = expense

    # Call post_expense
    result = await service.post_expense(
        expense_id=expense.id,
        actor_id=uuid4(),
    )

    assert result["status"] == "POSTED"
    assert result["is_balanced"] is True
    assert result["audit_event_id"] is not None
    assert len(result["ledger_entries"]) > 0

    # Verify all added entries in DB had non-null source_audit_event_id matching audit_event_id
    added_entries = [
        call.args[0] for call in mock_db.add.call_args_list
        if hasattr(call.args[0], "source_audit_event_id")
    ]
    assert len(added_entries) > 0, "Entries should be added to db"
    for entry in added_entries:
        assert entry.source_audit_event_id == result["audit_event_id"], (
            "source_audit_event_id must be populated before flush"
        )

    print("  -> PASSED: Ledger entries have valid source_audit_event_id before flush")


# ---------------------------------------------------------------------------
# Test 10: Double-Entry Ledger Balancing Invariant
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_double_entry_balancing_enforcement():
    print("[10/12] Testing Double-Entry Ledger Balancing Invariant...")
    from app.services.posting import PostingService
    from app.models.expense import Expense
    from app.models.enums import EntryType, LifecycleStatus

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    service = PostingService(mock_db)

    expense = Expense(
        id=uuid4(),
        project_id=uuid4(),
        source_event_id=uuid4(),
        subtotal=Decimal("500.00"),
        tax_amount=Decimal("0.00"),
        total=Decimal("500.00"),
        currency="INR",
        lifecycle_status=LifecycleStatus.RECONCILED,
    )
    mock_db.get.return_value = expense

    # 1. Balanced journal: Debits 500 == Credits 500
    account_id = uuid4()
    balanced_entries = [
        {"ledger_account_id": account_id, "entry_type": EntryType.DEBIT, "amount": Decimal("500.00")},
        {"ledger_account_id": account_id, "entry_type": EntryType.CREDIT, "amount": Decimal("500.00")},
    ]
    res = await service.post_expense(expense.id, actor_id=uuid4(), custom_entries=balanced_entries)
    assert res["is_balanced"] is True
    assert len(res["ledger_entries"]) == 2, "Balanced entries must be accepted"

    # 2. Unbalanced journal: Debits 500 != Credits 400
    unbalanced_entries = [
        {"ledger_account_id": account_id, "entry_type": EntryType.DEBIT, "amount": Decimal("500.00")},
        {"ledger_account_id": account_id, "entry_type": EntryType.CREDIT, "amount": Decimal("400.00")},
    ]
    with pytest.raises(ValueError, match="Double-entry"):
        await service.post_expense(expense.id, actor_id=uuid4(), custom_entries=unbalanced_entries)

    print("  -> PASSED: Balanced journals accepted, unbalanced journals rejected with ValueError")


# ---------------------------------------------------------------------------
# Test 11: Reconciliation Candidate Query Logic
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reconciliation_candidate_query():
    print("[11/12] Testing Reconciliation Candidate Query Logic...")
    from app.services.reconciliation import ReconciliationService
    from app.models.expense import Expense
    from app.models.payment_event import PaymentEvent
    from app.models.enums import PaymentMethod

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    service = ReconciliationService(mock_db)

    project_id = uuid4()
    expense = Expense(
        id=uuid4(),
        project_id=project_id,
        source_event_id=uuid4(),  # Receipt upload source event
        total=Decimal("1500.00"),
        transaction_date=date(2026, 9, 20),
        payment_method=PaymentMethod.UPI,
    )

    # Mock database return with a matching payment event
    payment = PaymentEvent(
        id=uuid4(),
        source_event_id=uuid4(),  # Separate bank feed source event!
        amount=Decimal("1500.00"),
        occurred_at=datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        payee_raw_text="Vendor Construction Supplies",
        payment_method=PaymentMethod.UPI,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [payment]
    mock_db.execute.return_value = mock_result

    # Ensure query succeeds and finds candidates when project_id is provided
    candidates = await service.find_candidates(expense, project_id=project_id)
    assert len(candidates) == 1, "Candidate should be found despite distinct source_event_ids"
    assert candidates[0]["payment_event_id"] == payment.id

    print("  -> PASSED: Candidate query operates without broken source_event_id join")


# ---------------------------------------------------------------------------
# Test 12: Reconciliation Confidence Heuristic & Payee Verification
# ---------------------------------------------------------------------------
def test_reconciliation_confidence_payee_requirement():
    print("[12/12] Testing Reconciliation Confidence Payee Requirement...")
    from app.services.reconciliation import ReconciliationService
    from app.models.expense import Expense
    from app.models.payment_event import PaymentEvent
    from app.models.enums import MatchBasis, PaymentMethod

    mock_db = MagicMock()
    service = ReconciliationService(mock_db)

    # 1. Exact amount and same date, but completely UNRELATED payee / absent vendor
    unrelated_expense = Expense(
        id=uuid4(),
        total=Decimal("5000.00"),
        transaction_date=date(2026, 9, 20),
        payment_method=PaymentMethod.BANK_TRANSFER,
        extraction_payload={"vendor_name": "Cement Corp"},
    )
    unrelated_payment = PaymentEvent(
        id=uuid4(),
        amount=Decimal("5000.00"),
        occurred_at=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
        payee_raw_text="Fancy Restaurant Pvt Ltd",
        payment_method=PaymentMethod.BANK_TRANSFER,
    )
    score_unrelated, basis_unrelated = service._calculate_match_score(
        unrelated_expense, unrelated_payment
    )
    assert score_unrelated <= Decimal("0.65"), (
        f"Score without payee similarity must be <= 0.65 (got {score_unrelated})"
    )
    assert score_unrelated < service.CONFIDENCE_THRESHOLD, (
        "Unrelated payee transaction must NOT reach auto-match confidence threshold (0.80)"
    )

    # 2. Exact amount, same date, and MATCHING payee
    matching_expense = Expense(
        id=uuid4(),
        total=Decimal("5000.00"),
        transaction_date=date(2026, 9, 20),
        payment_method=PaymentMethod.BANK_TRANSFER,
        extraction_payload={"vendor_name": "Ultratech Cement Limited"},
    )
    matching_payment = PaymentEvent(
        id=uuid4(),
        amount=Decimal("5000.00"),
        occurred_at=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
        payee_raw_text="Ultratech Cement Ltd",
        payment_method=PaymentMethod.BANK_TRANSFER,
    )
    score_matching, basis_matching = service._calculate_match_score(
        matching_expense, matching_payment
    )
    assert score_matching >= service.CONFIDENCE_THRESHOLD, (
        f"Score with matching payee should be >= 0.80 (got {score_matching})"
    )

    # 3. Exact UPI reference match -> 1.0
    ref_expense = Expense(
        id=uuid4(),
        total=Decimal("1200.00"),
        payment_method=PaymentMethod.UPI,
        extraction_payload={"upi_reference": "UPI987654321"},
    )
    ref_payment = PaymentEvent(
        id=uuid4(),
        amount=Decimal("1200.00"),
        payment_method=PaymentMethod.UPI,
        upi_reference="UPI987654321",
    )
    score_ref, basis_ref = service._calculate_match_score(ref_expense, ref_payment)
    assert score_ref == Decimal("1.0")
    assert basis_ref == MatchBasis.REFERENCE

    print("  -> PASSED: Unrelated payee scores capped at <= 0.65; matching payee scores >= 0.80")


# ---------------------------------------------------------------------------
# Main Execution Runner
# ---------------------------------------------------------------------------
async def run_all_checks():
    print("=" * 60)
    print("RUNNING PRIORITY 2 CORE BACKEND & INTEGRITY VERIFICATION SUITE")
    print("=" * 60 + "\n")

    test_celery_worker_entrypoint()
    test_celery_task_modules()
    await test_ocr_llm_job_linkage_and_handling()
    await test_expense_update_persistence()
    await test_manual_expense_category_persistence()
    test_celery_dispatch_after_commit()
    test_whatsapp_auth_token_usage()
    await test_ledger_posting_audit_event_flush_order()
    await test_double_entry_balancing_enforcement()
    await test_reconciliation_candidate_query()
    test_reconciliation_confidence_payee_requirement()

    print("\n" + "=" * 60)
    print("ALL 12 PRIORITY 2 CORE BACKEND CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_checks())
