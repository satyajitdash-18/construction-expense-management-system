"""Tests for reconciliation service and API."""

import pytest
import pytest_asyncio
from decimal import Decimal
from uuid import UUID, uuid4
from datetime import date, datetime, timedelta

from app.models.enums import (
    JobStatus,
    JobType,
    LifecycleStatus,
    MatchBasis,
    PaymentMethod,
    ReconciliationStatus,
    SourceType,
)
from app.models.expense import Expense
from app.models.payment_event import PaymentEvent
from app.models.reconciliation_record import ReconciliationRecord
from app.models.source_event import SourceEvent
from app.repositories.reconciliation import ReconciliationRepository
from app.services.reconciliation import ReconciliationService
from app.services.expense import ExpenseService


@pytest_asyncio.fixture
async def reconciliation_service(db_session):
    """Create reconciliation service."""
    return ReconciliationService(db_session)


@pytest_asyncio.fixture
async def reconciliation_repo(db_session):
    """Create reconciliation repository."""
    return ReconciliationRepository(db_session)


@pytest_asyncio.fixture
async def expense_service(db_session):
    """Create expense service."""
    return ExpenseService(db_session)


async def _create_test_expense_in_session(db_session, test_project, test_user, upi_reference="UPI123456789"):
    """Helper to create a test expense in STAGED status within the given session."""
    source_event = SourceEvent(
        source=SourceType.MANUAL,
        external_id=None,
        idempotency_key=str(uuid4()),
        raw_payload={"test": True},
    )
    db_session.add(source_event)
    await db_session.flush()

    expense = Expense(
        project_id=test_project.id,
        source_event_id=source_event.id,
        transaction_date=date(2026, 9, 20),
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("180.00"),
        total=Decimal("1180.00"),
        currency="INR",
        payment_method=PaymentMethod.UPI,
        lifecycle_status=LifecycleStatus.STAGED,
        extraction_payload={
            "upi_reference": upi_reference,
            "vendor_name": "Test Vendor",
        },
        confidence_score=Decimal("0.95"),
    )
    db_session.add(expense)
    await db_session.flush()
    await db_session.refresh(expense, attribute_names=["vendor", "source_event"])
    return expense


async def _create_test_payment_event_in_session(db_session, upi_reference="UPI123456789"):
    """Helper to create a matching payment event within the given session."""
    source_event = SourceEvent(
        source=SourceType.SMS_UPI,
        external_id="sms_123",
        idempotency_key=str(uuid4()),
        raw_payload={"source": "sms"},
    )
    db_session.add(source_event)
    await db_session.flush()

    payment_event = PaymentEvent(
        source_event_id=source_event.id,
        amount=Decimal("1180.00"),
        occurred_at=datetime(2026, 9, 20, 10, 30),
        payee_raw_text="Test Vendor",
        upi_reference=upi_reference,
        bank_reference=None,
        payment_method=PaymentMethod.UPI,
        device_id="device_123",
        raw_text="UPI payment to Test Vendor",
        idempotency_key=str(uuid4()),
    )
    db_session.add(payment_event)
    await db_session.flush()
    await db_session.refresh(payment_event)
    return payment_event


class TestReconciliationRepository:
    """Tests for reconciliation repository."""

    @pytest.mark.asyncio
    async def test_get_unmatched_expenses(self, reconciliation_repo, db_session, test_project, test_user):
        """Test getting unmatched expenses."""
        expense = await _create_test_expense_in_session(db_session, test_project, test_user)
        expenses = await reconciliation_repo.get_unmatched_expenses()
        assert len(expenses) >= 1
        assert expense.id in [e.id for e in expenses]

    @pytest.mark.asyncio
    async def test_get_unmatched_payment_events(self, reconciliation_repo, db_session):
        """Test getting unmatched payment events."""
        payment_event = await _create_test_payment_event_in_session(db_session)
        payment_events = await reconciliation_repo.get_unmatched_payment_events()
        assert len(payment_events) >= 1
        assert payment_event.id in [p.id for p in payment_events]

    @pytest.mark.asyncio
    async def test_find_exact_reference_match(self, reconciliation_repo, db_session, test_project, test_user):
        """Test Tier 1 exact reference match."""
        unique_upi = f"UPI{uuid4().hex[:8]}"
        expense = await _create_test_expense_in_session(db_session, test_project, test_user, upi_reference=unique_upi)
        payment_event = await _create_test_payment_event_in_session(db_session, upi_reference=unique_upi)
        match = await reconciliation_repo.find_exact_reference_match(expense)
        assert match is not None
        assert match.upi_reference == unique_upi

    @pytest.mark.asyncio
    async def test_find_exact_reference_match_no_ref(self, reconciliation_repo, db_session, test_project, test_user):
        """Test Tier 1 exact reference match when no reference."""
        expense = await _create_test_expense_in_session(db_session, test_project, test_user, upi_reference=None)
        payment_event = await _create_test_payment_event_in_session(db_session, upi_reference=None)
        match = await reconciliation_repo.find_exact_reference_match(expense)
        assert match is None

    @pytest.mark.asyncio
    async def test_find_candidates_for_expense(self, reconciliation_repo, db_session, test_project, test_user):
        """Test finding candidate payment events."""
        expense = await _create_test_expense_in_session(db_session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(db_session)
        candidates = await reconciliation_repo.find_candidates_for_expense(expense)
        assert len(candidates) >= 1
        assert payment_event.id in [c.id for c in candidates]


class TestReconciliationService:
    """Tests for reconciliation service."""

    @pytest.mark.asyncio
    async def test_reconcile_tier1_exact_match(self, reconciliation_service, test_project, test_user):
        """Test Tier 1 exact reference match."""
        unique_upi = f"UPI{uuid4().hex[:8]}"
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user, upi_reference=unique_upi)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session, upi_reference=unique_upi)

        reconciliation = await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        assert reconciliation.status == ReconciliationStatus.MATCHED
        assert reconciliation.match_basis == MatchBasis.REFERENCE
        assert reconciliation.match_score == 1.0
        assert reconciliation.payment_event_id == payment_event.id

        # Check expense status updated
        await reconciliation_service.session.refresh(expense)
        assert expense.lifecycle_status == LifecycleStatus.RECONCILED

    @pytest.mark.asyncio
    async def test_reconcile_tier2_scored_match(self, reconciliation_service, test_project, test_user):
        """Test Tier 2 scored match when no exact reference."""
        from app.models.vendor import Vendor
        
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user, upi_reference=None)
        
        # Create a vendor and associate with expense
        vendor = Vendor(name="Test Vendor")
        reconciliation_service.session.add(vendor)
        await reconciliation_service.session.flush()
        expense.vendor_id = vendor.id
        await reconciliation_service.session.flush()
        await reconciliation_service.session.refresh(expense, attribute_names=["vendor"])
        
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session, upi_reference=None)

        reconciliation = await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        # Should match on amount + date + vendor
        assert reconciliation.status == ReconciliationStatus.MATCHED
        assert reconciliation.match_basis == MatchBasis.SCORED
        assert reconciliation.match_score >= 0.6  # Above ambiguous threshold

    @pytest.mark.asyncio
    async def test_reconcile_manual(self, reconciliation_service, test_project, test_user):
        """Test manual reconciliation with specific payment event."""
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session)

        reconciliation = await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            payment_event_id=payment_event.id,
            auto_match=False,
        )

        assert reconciliation.status == ReconciliationStatus.MATCHED
        assert reconciliation.match_basis == MatchBasis.MANUAL
        assert reconciliation.payment_event_id == payment_event.id

    @pytest.mark.asyncio
    async def test_reconcile_already_reconciled(self, reconciliation_service, test_project, test_user):
        """Test reconciling already reconciled expense returns existing record."""
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session)

        # First reconciliation
        first_reconciliation = await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        # Second attempt
        second_reconciliation = await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        assert second_reconciliation.id == first_reconciliation.id
        assert second_reconciliation.status == ReconciliationStatus.MATCHED

    @pytest.mark.asyncio
    async def test_reconcile_no_match_creates_unmatched(self, reconciliation_service, test_project, test_user):
        """Test reconciliation creates UNMATCHED when no candidates."""
        from app.models.payment_event import PaymentEvent
        from sqlalchemy import delete
        
        # Use the service's session
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user, upi_reference=None)

        # Delete any matching payment events
        from app.models.payment_event import PaymentEvent
        from sqlalchemy import delete
        await reconciliation_service.session.execute(
            delete(PaymentEvent)
        )
        await reconciliation_service.session.commit()

        reconciliation = await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        assert reconciliation.status == ReconciliationStatus.UNMATCHED
        assert reconciliation.payment_event_id is None

    @pytest.mark.asyncio
    async def test_auto_match_batch(self, reconciliation_service, test_project, test_user):
        """Test batch auto-matching."""
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session)

        result = await reconciliation_service.auto_match_batch(
            confidence_threshold=0.8,
        )

        assert result["processed"] >= 1
        assert result["matched"] >= 1
        assert result["matches"] is not None

    @pytest.mark.asyncio
    async def test_auto_match_batch_dry_run(self, reconciliation_service, test_project, test_user):
        """Test batch auto-matching dry run doesn't persist."""
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session)

        result = await reconciliation_service.auto_match_batch(
            confidence_threshold=0.8,
            dry_run=True,
        )

        assert result["processed"] >= 1
        assert result["matched"] >= 1

        # Expense should still be STAGED
        from app.models.expense import Expense
        await reconciliation_service.session.refresh(expense)
        assert expense.lifecycle_status == LifecycleStatus.STAGED

    @pytest.mark.asyncio
    async def test_reject_reconciliation(self, reconciliation_service, test_project, test_user):
        """Test rejecting a reconciliation."""
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session)

        await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        reconciliation = await reconciliation_service.reject_reconciliation(
            expense_id=expense.id,
            reviewer_id=test_user.id,
            notes="Wrong payment event",
        )

        assert reconciliation.status == ReconciliationStatus.UNMATCHED

    @pytest.mark.asyncio
    async def test_unmatch_reconciliation(self, reconciliation_service, test_project, test_user):
        """Test unmatching a reconciled expense."""
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session)

        await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        reconciliation = await reconciliation_service.unmatch_reconciliation(
            expense_id=expense.id,
            reviewer_id=test_user.id,
            notes="Wrong match",
        )

        assert reconciliation.status == ReconciliationStatus.UNMATCHED
        assert reconciliation.payment_event_id is None

        await reconciliation_service.session.refresh(expense)
        assert expense.lifecycle_status == LifecycleStatus.STAGED

    @pytest.mark.asyncio
    async def test_get_reconciliation_stats(self, reconciliation_service, test_project, test_user):
        """Test getting reconciliation statistics."""
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session)

        await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        stats = await reconciliation_service.get_reconciliation_stats()

        assert stats["total"] >= 1
        assert stats["matched"] >= 1

    @pytest.mark.asyncio
    async def test_list_reconciliations(self, reconciliation_service, test_project, test_user):
        """Test listing reconciliations."""
        expense = await _create_test_expense_in_session(reconciliation_service.session, test_project, test_user)
        payment_event = await _create_test_payment_event_in_session(reconciliation_service.session)

        await reconciliation_service.reconcile_expense(
            expense_id=expense.id,
            auto_match=True,
        )

        result = await reconciliation_service.list_reconciliations(page=1, page_size=10)

        assert result["total"] >= 1
        assert len(result["items"]) >= 1


async def _create_test_expense_in_session(db_session, test_project, test_user, upi_reference="UPI123456789"):
    """Helper to create a test expense in STAGED status within the given session."""
    source_event = SourceEvent(
        source=SourceType.MANUAL,
        external_id=None,
        idempotency_key=str(uuid4()),
        raw_payload={"test": True},
    )
    db_session.add(source_event)
    await db_session.flush()

    expense = Expense(
        project_id=test_project.id,
        source_event_id=source_event.id,
        transaction_date=date(2026, 9, 20),
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("180.00"),
        total=Decimal("1180.00"),
        currency="INR",
        payment_method=PaymentMethod.UPI,
        lifecycle_status=LifecycleStatus.STAGED,
        extraction_payload={
            "upi_reference": upi_reference,
            "vendor_name": "Test Vendor",
        },
        confidence_score=Decimal("0.95"),
    )
    db_session.add(expense)
    await db_session.flush()
    await db_session.refresh(expense, attribute_names=["vendor", "source_event"])
    return expense


async def _create_test_payment_event_in_session(db_session, upi_reference="UPI123456789"):
    """Helper to create a matching payment event within the given session."""
    external_id = f"sms_{uuid4().hex[:8]}"
    source_event = SourceEvent(
        source=SourceType.SMS_UPI,
        external_id=external_id,
        idempotency_key=str(uuid4()),
        raw_payload={"source": "sms"},
    )
    db_session.add(source_event)
    await db_session.flush()

    payment_event = PaymentEvent(
        source_event_id=source_event.id,
        amount=Decimal("1180.00"),
        occurred_at=datetime(2026, 9, 20, 10, 30),
        payee_raw_text="Test Vendor",
        upi_reference=upi_reference,
        bank_reference=None,
        payment_method=PaymentMethod.UPI,
        device_id="device_123",
        raw_text="UPI payment to Test Vendor",
        idempotency_key=str(uuid4()),
    )
    db_session.add(payment_event)
    await db_session.flush()
    await db_session.refresh(payment_event)
    return payment_event


from datetime import datetime
from uuid import uuid4
from decimal import Decimal
from app.models.enums import (
    JobStatus,
    JobType,
    LifecycleStatus,
    MatchBasis,
    PaymentMethod,
    ReconciliationStatus,
    SourceType,
)
from app.models.expense import Expense
from app.models.payment_event import PaymentEvent
from app.models.reconciliation_record import ReconciliationRecord
from app.models.source_event import SourceEvent
from app.repositories.reconciliation import ReconciliationRepository
from app.services.reconciliation import ReconciliationService
from app.services.expense import ExpenseService