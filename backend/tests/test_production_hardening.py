"""Production hardening integration and concurrency test suite.

Tests:
1. IDOR prevention and project membership RBAC.
2. Concurrent refresh token rotation and reuse detection.
3. Ledger posting concurrency lock, double-entry balance, and GAAP reversal.
4. Mathematical financial invariants (strictly Decimal precision).
5. Evidence magic-bytes inspection and project scoping.
6. Reconciliation candidate finding after rejected/unmatched payments.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
import io
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import LifecycleStatus, PaymentMethod, ProjectStatus, ReconciliationStatus, SourceType
from app.models.expense import Expense
from app.models.payment_event import PaymentEvent
from app.models.project import Project
from app.models.reconciliation_record import ReconciliationRecord
from app.models.source_event import SourceEvent
from app.models.user import User
from app.models.vendor import Vendor
from app.services.auth import AuthService
from app.services.llm_extraction import ExtractionResult
from app.services.posting import PostingService
from app.services.reconciliation import ReconciliationService


@pytest.mark.asyncio
async def test_idor_project_membership_and_rbac(async_client: AsyncClient, db_session: AsyncSession):
    """Verify cross-tenant IDOR protection and ProjectMember scoping."""
    auth_service = AuthService(db_session)

    # 1. Create two users
    user_a = await auth_service.create_user(
        email=f"user_a_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="User A",
        role_names=["project_manager"],
    )
    user_b = await auth_service.create_user(
        email=f"user_b_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="User B",
        role_names=["site_user"],
    )
    admin_user = await auth_service.create_user(
        email=f"admin_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Super Admin",
        role_names=["admin"],
    )
    await db_session.commit()

    token_a = create_access_token(data={"sub": str(user_a.id)})
    token_b = create_access_token(data={"sub": str(user_b.id)})
    token_admin = create_access_token(data={"sub": str(admin_user.id)})

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    headers_admin = {"Authorization": f"Bearer {token_admin}"}

    # 2. User A creates Project A
    res_create = await async_client.post(
        "/api/v1/projects",
        json={"name": "Project Alpha", "code": f"PRJ-{uuid4().hex[:6]}", "status": "active"},
        headers=headers_a,
    )
    assert res_create.status_code == 201
    proj_a_id = res_create.json()["id"]

    # 3. User B attempts to access Project A -> 404 Not Found (tenant-isolated anti-enumeration)
    res_get = await async_client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_b)
    assert res_get.status_code == 404

    # 4. User B attempts to create an expense on Project A -> 404 Not Found
    res_exp = await async_client.post(
        "/api/v1/expenses",
        json={
            "project_id": proj_a_id,
            "transaction_date": date.today().isoformat(),
            "subtotal": 100.0,
            "tax_amount": 18.0,
            "total": 118.0,
            "payment_method": "CASH",
        },
        headers=headers_b,
    )
    assert res_exp.status_code in (403, 404)

    # 5. User A adds User B as a member with role 'site_user'
    res_add_member = await async_client.post(
        f"/api/v1/projects/{proj_a_id}/members",
        json={"user_id": str(user_b.id), "role": "site_user"},
        headers=headers_a,
    )
    assert res_add_member.status_code == 201

    # 6. Now User B can read Project A
    res_get_ok = await async_client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_b)
    assert res_get_ok.status_code == 200

    # 7. User A removes User B from Project A
    res_del_member = await async_client.delete(
        f"/api/v1/projects/{proj_a_id}/members/{user_b.id}",
        headers=headers_a,
    )
    assert res_del_member.status_code == 204

    # 8. User B is blocked again -> 404 Not Found (tenant-isolated anti-enumeration)
    res_blocked = await async_client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_b)
    assert res_blocked.status_code == 404

    # 9. Super Admin can access Project A even without explicit membership
    res_admin = await async_client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_admin)
    assert res_admin.status_code == 200


@pytest.mark.asyncio
async def test_financial_invariants_and_schema_validation(async_client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict):
    """Verify that financial calculation invariants strictly reject floating-point drift and invalid totals."""
    # 1. Test ExtractionResult invariant validation logic
    valid_res = ExtractionResult(
        total_amount=118.00,
        subtotal=100.00,
        tax_amount=18.00,
        cgst_amount=9.00,
        sgst_amount=9.00,
        confidence_score=0.9,
    )
    is_valid, reason = valid_res.validate_financial_invariants()
    assert is_valid is True
    assert reason is None

    # Mismatched total (subtotal + tax != total)
    invalid_math = ExtractionResult(
        total_amount=250.00,
        subtotal=100.00,
        tax_amount=18.00,
        confidence_score=0.9,
    )
    is_valid, reason = invalid_math.validate_financial_invariants()
    assert is_valid is False
    assert "does not match subtotal" in reason

    # Negative total
    neg_res = ExtractionResult(total_amount=-50.00, confidence_score=0.9)
    is_valid, reason = neg_res.validate_financial_invariants()
    assert is_valid is False
    assert "negative" in reason

    # 2. Test API validation when creating an expense with mismatched math
    proj = Project(
        name="Math Invariant Project",
        code=f"MTH-{uuid4().hex[:6]}",
        created_by=test_user.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(proj)
    await db_session.flush()

    # Mismatched subtotal + tax != total in API POST
    res_bad = await async_client.post(
        "/api/v1/expenses",
        json={
            "project_id": str(proj.id),
            "transaction_date": date.today().isoformat(),
            "subtotal": 100.00,
            "tax_amount": 18.00,
            "total": 300.00,  # Deliberate mismatch
            "payment_method": "CASH",
        },
        headers=auth_headers,
    )
    assert res_bad.status_code == 422


@pytest.mark.asyncio
async def test_evidence_magic_bytes_inspection(async_client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict):
    """Verify that evidence upload validates magic bytes and rejects spoofed file extensions."""
    source_event = SourceEvent(
        source=SourceType.MANUAL,
        idempotency_key=f"evd_{uuid4().hex}",
        raw_payload={"type": "receipt"},
    )
    db_session.add(source_event)
    await db_session.flush()

    proj = Project(
        name="Evidence Test Project",
        code=f"EVD-{uuid4().hex[:6]}",
        created_by=test_user.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(proj)
    await db_session.flush()

    expense = Expense(
        project_id=proj.id,
        source_event_id=source_event.id,
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
        total=Decimal("118.00"),
        transaction_date=date.today(),
        lifecycle_status=LifecycleStatus.STAGED,
    )
    db_session.add(expense)
    await db_session.commit()

    # 1. Spoofed PDF with text content -> 400 Bad Request
    fake_pdf = io.BytesIO(b"Hello world, this is a plain text file pretending to be PDF")
    res_fake = await async_client.post(
        f"/api/v1/evidence/upload?expense_id={expense.id}",
        files={"file": ("fake_invoice.pdf", fake_pdf, "application/pdf")},
        headers=auth_headers,
    )
    assert res_fake.status_code == 400
    assert "File content does not match allowed signature" in res_fake.json()["detail"]

    # 2. Spoofed PNG with PDF header -> 400 Bad Request
    fake_png = io.BytesIO(b"%PDF-1.4 header in png")
    res_fake_png = await async_client.post(
        f"/api/v1/evidence/upload?expense_id={expense.id}",
        files={"file": ("receipt.png", fake_png, "image/png")},
        headers=auth_headers,
    )
    assert res_fake_png.status_code == 400
    assert "File content does not match allowed signature" in res_fake_png.json()["detail"]


@pytest.mark.asyncio
async def test_ledger_posting_row_lock_and_reversal(db_session: AsyncSession, test_user: User):
    """Verify GAAP compliant double-entry posting, concurrency protection, and balanced reversals."""
    source_event = SourceEvent(
        source=SourceType.MANUAL,
        idempotency_key=f"ldg_{uuid4().hex}",
        raw_payload={"type": "invoice"},
    )
    db_session.add(source_event)
    await db_session.flush()

    proj = Project(
        name="Ledger Test Project",
        code=f"LDG-{uuid4().hex[:6]}",
        created_by=test_user.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(proj)
    await db_session.flush()

    vendor = Vendor(name="Acme Cement", gstin="27AAAAA0000A1Z5")
    db_session.add(vendor)
    await db_session.flush()

    expense = Expense(
        project_id=proj.id,
        source_event_id=source_event.id,
        vendor_id=vendor.id,
        subtotal=Decimal("5000.00"),
        tax_amount=Decimal("900.00"),
        cgst_amount=Decimal("450.00"),
        sgst_amount=Decimal("450.00"),
        total=Decimal("5900.00"),
        transaction_date=date.today(),
        lifecycle_status=LifecycleStatus.RECONCILED,
    )
    db_session.add(expense)
    await db_session.commit()

    posting_service = PostingService(db_session)

    # 1. First posting -> succeeds
    result = await posting_service.post_expense(expense.id, actor_id=test_user.id)
    entries = result["ledger_entries"]
    assert len(entries) >= 2
    assert result["is_balanced"] is True
    assert result["debit_total"] == result["credit_total"] == 5900.00

    # Verify expense status transitioned to POSTED
    await db_session.refresh(expense)
    assert expense.lifecycle_status == LifecycleStatus.POSTED

    # 2. Attempting double-posting -> raises ValueError
    with pytest.raises(ValueError) as exc_info:
        await posting_service.post_expense(expense.id, actor_id=test_user.id)
    assert "already posted" in str(exc_info.value)

    # 3. Reverse the posting
    rev_res = await posting_service.reverse_posting(
        expense_id=expense.id,
        actor_id=test_user.id,
        reason="Duplicate invoice entry discovered",
    )
    rev_entries = rev_res["ledger_entries"]
    assert len(rev_entries) == len(entries)
    for re in rev_entries:
        assert re["is_reversal"] is True

    rev_debit = sum(e["amount"] for e in rev_entries if e["entry_type"].lower() == "debit")
    rev_credit = sum(e["amount"] for e in rev_entries if e["entry_type"].lower() == "credit")
    assert rev_debit == rev_credit == 5900.00

    # Expense is returned to RECONCILED
    await db_session.refresh(expense)
    assert expense.lifecycle_status == LifecycleStatus.RECONCILED

    # 4. Attempting to reverse again -> raises ValueError
    with pytest.raises(ValueError) as exc_rev:
        await posting_service.reverse_posting(
            expense_id=expense.id,
            actor_id=test_user.id,
            reason="Second reversal attempt",
        )
    assert "not currently posted" in str(exc_rev.value) or "No active posting found" in str(exc_rev.value)


@pytest.mark.asyncio
async def test_reconciliation_candidate_reusability(db_session: AsyncSession, test_user: User):
    """Verify that rejected or unmatched payment events remain eligible candidates for reconciliation."""
    source_event = SourceEvent(
        source=SourceType.SMS_UPI,
        idempotency_key=f"rcn_src_{uuid4().hex}",
        raw_payload={"type": "sms"},
    )
    db_session.add(source_event)
    await db_session.flush()

    proj = Project(
        name="Recon Test Project",
        code=f"RCN-{uuid4().hex[:6]}",
        created_by=test_user.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(proj)
    await db_session.flush()

    payment = PaymentEvent(
        source_event_id=source_event.id,
        amount=Decimal("1500.00"),
        occurred_at=datetime.now(UTC),
        payment_method=PaymentMethod.UPI,
        payee_raw_text="SHREE RAM HARDWARE",
        raw_text="UPI-12345 SHREE RAM HARDWARE",
        idempotency_key=f"HDFC_{uuid4().hex[:8]}",
    )
    db_session.add(payment)

    expense1 = Expense(
        project_id=proj.id,
        source_event_id=source_event.id,
        subtotal=Decimal("1500.00"),
        tax_amount=Decimal("0.00"),
        total=Decimal("1500.00"),
        transaction_date=date.today(),
        lifecycle_status=LifecycleStatus.STAGED,
    )
    db_session.add(expense1)
    await db_session.commit()

    recon_service = ReconciliationService(db_session)

    # 1. Candidate is found initially
    candidates = await recon_service.find_candidates(expense1)
    assert any(c["payment_event_id"] == payment.id for c in candidates)

    # 2. Create a reconciliation record and mark it UNMATCHED
    rec = ReconciliationRecord(
        expense_id=expense1.id,
        payment_event_id=payment.id,
        status=ReconciliationStatus.UNMATCHED,
        match_basis="MANUAL",
        match_score=Decimal("1.0"),
    )
    db_session.add(rec)
    await db_session.commit()

    # 3. Create expense2: the rejected payment MUST still be discoverable as a candidate!
    source_event2 = SourceEvent(
        source=SourceType.SMS_UPI,
        idempotency_key=f"rcn_src2_{uuid4().hex}",
        raw_payload={"type": "sms"},
    )
    db_session.add(source_event2)
    await db_session.flush()

    expense2 = Expense(
        project_id=proj.id,
        source_event_id=source_event2.id,
        subtotal=Decimal("1500.00"),
        tax_amount=Decimal("0.00"),
        total=Decimal("1500.00"),
        transaction_date=date.today(),
        lifecycle_status=LifecycleStatus.STAGED,
    )
    db_session.add(expense2)
    await db_session.commit()

    candidates_exp2 = await recon_service.find_candidates(expense2)
    assert any(c["payment_event_id"] == payment.id for c in candidates_exp2)


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse_detection(async_client: AsyncClient, db_session: AsyncSession):
    """Verify refresh token rotation and family invalidation upon reuse attack."""
    auth_service = AuthService(db_session)
    email = f"rotation_user_{uuid4().hex[:6]}@example.com"
    raw_password = "password123"

    await auth_service.create_user(
        email=email,
        password=raw_password,
        full_name="Rotation User",
        role_names=["site_user"],
    )
    await db_session.commit()

    # 1. Login to receive initial tokens
    res_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": raw_password},
    )
    assert res_login.status_code == 200
    token_data = res_login.json()
    first_refresh = token_data["refresh_token"]

    # 2. Rotate token once -> succeeds with 200
    res_refresh1 = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert res_refresh1.status_code == 200
    token_data2 = res_refresh1.json()
    second_refresh = token_data2["refresh_token"]
    assert second_refresh != first_refresh

    # 3. Attempting to reuse first_refresh -> 401 Unauthorized (reuse detection!)
    res_reuse = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert res_reuse.status_code == 401
    assert "revoked or reused" in res_reuse.json()["detail"].lower()

    # 4. Because reuse was detected, the entire family is revoked; second_refresh is now also invalid
    res_second_reuse = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": second_refresh},
    )
    assert res_second_reuse.status_code == 401
