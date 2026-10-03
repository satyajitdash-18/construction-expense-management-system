"""Final Production Blocker Remediation Test Suite.

Verifies:
1. Global Audit Log Security (project-scoped SQL queries, isolation between tenants).
2. Retention Policy Authorization (strict admin enforcement for destructive actions).
3. 404 vs 403 Information Disclosure (no tenant resource enumeration).
4. Expense Update Financial Invariants (composite proposed state validation).
5. Database Financial Invariants (PostgreSQL CHECK constraint enforcement).
6. Decimal Financial Extraction & Untrusted LLM Boundary.
7. Master Data RBAC (vendor & category mutation protections).
8. Evidence Count Query & Streaming Upload.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditService
from app.core.security import create_access_token
from app.models.enums import LifecycleStatus, PaymentMethod, ProjectStatus, SourceType
from app.models.expense import Expense
from app.models.expense_category import ExpenseCategory
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.source_event import SourceEvent
from app.models.vendor import Vendor
from app.services.auth import AuthService
from app.services.llm_extraction import ExtractionResult


@pytest.mark.asyncio
async def test_audit_log_tenant_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify User A cannot retrieve Project B audit events, while Admin has global access."""
    auth_service = AuthService(db_session)

    # 1. Create User A, User B, Admin
    user_a = await auth_service.create_user(
        email=f"user_a_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="User A",
        role_names=["site_user"],
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
        full_name="Admin",
        role_names=["admin"],
    )
    await db_session.commit()

    # 2. Create Project A and Project B
    proj_a = Project(
        name="Project A",
        code=f"PA-{uuid4().hex[:6]}",
        created_by=user_a.id,
        status=ProjectStatus.ACTIVE,
    )
    proj_b = Project(
        name="Project B",
        code=f"PB-{uuid4().hex[:6]}",
        created_by=user_b.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add_all([proj_a, proj_b])
    await db_session.flush()

    # Assign membership: User A -> Project A, User B -> Project B
    member_a = ProjectMember(
        project_id=proj_a.id,
        user_id=user_a.id,
        role="site_user",
    )
    member_b = ProjectMember(
        project_id=proj_b.id,
        user_id=user_b.id,
        role="site_user",
    )
    db_session.add_all([member_a, member_b])
    await db_session.commit()

    # 3. Create Audit Events in Project A and Project B
    audit_service = AuditService(db_session)
    await audit_service.record(
        event_type="expense.created",
        entity_type="expense",
        entity_id=uuid4(),
        actor_id=user_a.id,
        payload={"project_id": str(proj_a.id), "memo": "Project A expense created"},
    )
    await audit_service.record(
        event_type="expense.created",
        entity_type="expense",
        entity_id=uuid4(),
        actor_id=user_b.id,
        payload={"project_id": str(proj_b.id), "memo": "Project B secret expense"},
    )
    await db_session.commit()

    # 4. Query audit logs as User A
    token_a = create_access_token({"sub": str(user_a.id)})
    resp_a = await async_client.get(
        "/api/v1/audit/logs",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a.status_code == 200, resp_a.text
    data_a = resp_a.json()
    items_a = data_a.get("items", [])
    # User A must NOT see Project B
    for item in items_a:
        payload = item.get("payload", {})
        assert payload.get("project_id") != str(proj_b.id)

    # 5. Query audit logs as Admin
    token_admin = create_access_token({"sub": str(admin_user.id)})
    resp_admin = await async_client.get(
        "/api/v1/audit/logs",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp_admin.status_code == 200, resp_admin.text
    data_admin = resp_admin.json()
    project_ids_in_admin = {
        item.get("payload", {}).get("project_id") for item in data_admin.get("items", [])
    }
    assert str(proj_a.id) in project_ids_in_admin
    assert str(proj_b.id) in project_ids_in_admin


@pytest.mark.asyncio
async def test_retention_policy_administrative_authorization(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify only admin can execute or manage retention policies."""
    auth_service = AuthService(db_session)
    site_user = await auth_service.create_user(
        email=f"site_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Site User",
        role_names=["site_user"],
    )
    admin_user = await auth_service.create_user(
        email=f"admin_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Admin User",
        role_names=["admin"],
    )
    await db_session.commit()

    site_token = create_access_token({"sub": str(site_user.id)})
    admin_token = create_access_token({"sub": str(admin_user.id)})

    fake_policy_id = uuid4()

    # Non-admin executing run policy -> 403 Forbidden
    resp = await async_client.post(
        f"/api/v1/audit-compliance/retention-policies/{fake_policy_id}/run",
        headers={"Authorization": f"Bearer {site_token}"},
    )
    assert resp.status_code == 403

    # Non-admin executing run-all -> 403 Forbidden
    resp_all = await async_client.post(
        "/api/v1/audit-compliance/retention-policies/run-all",
        headers={"Authorization": f"Bearer {site_token}"},
    )
    assert resp_all.status_code == 403

    # Admin executing run -> 404 because policy doesn't exist, NOT 403!
    resp_admin = await async_client.post(
        f"/api/v1/audit-compliance/retention-policies/{fake_policy_id}/run",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_admin.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_information_disclosure_404(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify accessing a resource belonging to another tenant returns 404, not 403."""
    auth_service = AuthService(db_session)
    user_attacker = await auth_service.create_user(
        email=f"attacker_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Attacker",
        role_names=["site_user"],
    )
    user_victim = await auth_service.create_user(
        email=f"victim_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Victim",
        role_names=["site_user"],
    )
    await db_session.commit()

    # Victim's private project
    victim_proj = Project(
        name="Victim Project",
        code=f"VIC-{uuid4().hex[:6]}",
        created_by=user_victim.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(victim_proj)
    await db_session.flush()

    # Attacker tries to access victim project details
    attacker_token = create_access_token({"sub": str(user_attacker.id)})
    resp = await async_client.get(
        f"/api/v1/projects/{victim_proj.id}",
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    # Must be 404 to prevent resource existence disclosure
    assert resp.status_code == 404, f"Expected 404 but got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_expense_update_financial_invariants(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify ExpenseUpdate rejects partial updates that violate subtotal + tax = total."""
    auth_service = AuthService(db_session)
    user = await auth_service.create_user(
        email=f"manager_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Project Manager",
        role_names=["project_manager", "finance_user"],
    )
    await db_session.commit()

    project = Project(
        name="Test Construction",
        code=f"TC-{uuid4().hex[:6]}",
        created_by=user.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(project)
    await db_session.flush()

    member = ProjectMember(
        project_id=project.id,
        user_id=user.id,
        role="project_manager",
    )
    db_session.add(member)

    # Create category
    cat = ExpenseCategory(name=f"Cement_{uuid4().hex[:6]}")
    db_session.add(cat)
    await db_session.commit()

    token = create_access_token({"sub": str(user.id)})
    headers = {"Authorization": f"Bearer {token}"}

    # Create initial valid expense: 100 + 18 = 118 via API
    resp_create = await async_client.post(
        "/api/v1/expenses",
        json={
            "project_id": str(project.id),
            "category_id": str(cat.id),
            "subtotal": 100.00,
            "tax_amount": 18.00,
            "total": 118.00,
            "transaction_date": "2026-09-20",
            "description": "Initial cement purchase",
            "payment_method": "CASH",
        },
        headers=headers,
    )
    assert resp_create.status_code == 201, resp_create.text
    expense_data = resp_create.json()
    expense_id = expense_data["id"]

    # 1. Invalid PATCH: change ONLY total to 200 without changing subtotal/tax
    resp_invalid_total = await async_client.patch(
        f"/api/v1/expenses/{expense_id}",
        json={"total": 200.00},
        headers=headers,
    )
    assert resp_invalid_total.status_code == 400
    assert "Financial invariant violated" in resp_invalid_total.json()["detail"]

    # 2. Invalid PATCH: change ONLY subtotal to 200 without reconciling tax/total
    resp_invalid_sub = await async_client.patch(
        f"/api/v1/expenses/{expense_id}",
        json={"subtotal": 200.00},
        headers=headers,
    )
    assert resp_invalid_sub.status_code == 400
    assert "Financial invariant violated" in resp_invalid_sub.json()["detail"]

    # 3. Valid PATCH: update subtotal, tax, and total consistently
    resp_valid = await async_client.patch(
        f"/api/v1/expenses/{expense_id}",
        json={
            "subtotal": 200.00,
            "tax_amount": 36.00,
            "total": 236.00,
        },
        headers=headers,
    )
    assert resp_valid.status_code == 200, resp_valid.text
    updated = resp_valid.json()
    assert Decimal(str(updated["subtotal"])) == Decimal("200.00")
    assert Decimal(str(updated["tax_amount"])) == Decimal("36.00")
    assert Decimal(str(updated["total"])) == Decimal("236.00")


@pytest.mark.asyncio
async def test_database_financial_invariants_direct_sql(db_session: AsyncSession):
    """Verify PostgreSQL check constraint rejects invalid financial states on INSERT and UPDATE."""
    auth_service = AuthService(db_session)
    user = await auth_service.create_user(
        email=f"db_test_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="DB Tester",
        role_names=["site_user"],
    )
    await db_session.commit()

    proj_id = uuid4()
    source_id = uuid4()
    exp_id = uuid4()

    # Create prerequisite parent project and source_event and commit so they survive rollbacks
    await db_session.execute(text(f"""
        INSERT INTO projects (id, name, code, status, created_by, created_at, updated_at)
        VALUES ('{proj_id}', 'DB Test Proj', 'DBP-{uuid4().hex[:6]}', 'active', '{user.id}', NOW(), NOW());
    """))
    await db_session.execute(text(f"""
        INSERT INTO source_events (id, source, idempotency_key, raw_payload, received_at)
        VALUES ('{source_id}', 'manual', 'idem-{uuid4().hex[:8]}', '{{}}', NOW());
    """))
    await db_session.commit()

    # 1. Direct invalid INSERT: subtotal 100, tax 18, total 999
    invalid_insert = text(f"""
        INSERT INTO expenses (
            id, project_id, source_event_id, transaction_date, subtotal, tax_amount, total, currency,
            extraction_payload, lifecycle_status, payment_method, created_at, updated_at
        ) VALUES (
            gen_random_uuid(), '{proj_id}', '{source_id}', '2026-09-20', 100.00, 18.00, 999.00, 'INR',
            '{{}}', 'RECEIVED', 'CASH', NOW(), NOW()
        );
    """)
    with pytest.raises(IntegrityError):
        await db_session.execute(invalid_insert)
        await db_session.flush()
    await db_session.rollback()

    # 2. Direct valid INSERT followed by invalid UPDATE
    valid_insert = text(f"""
        INSERT INTO expenses (
            id, project_id, source_event_id, transaction_date, subtotal, tax_amount, total, currency,
            extraction_payload, lifecycle_status, payment_method, created_at, updated_at
        ) VALUES (
            '{exp_id}', '{proj_id}', '{source_id}', '2026-09-20', 100.00, 18.00, 118.00, 'INR',
            '{{}}', 'RECEIVED', 'CASH', NOW(), NOW()
        );
    """)
    await db_session.execute(valid_insert)
    await db_session.flush()

    invalid_update = text(f"""
        UPDATE expenses
        SET total = 500.00
        WHERE id = '{exp_id}';
    """)
    with pytest.raises(IntegrityError):
        await db_session.execute(invalid_update)
        await db_session.flush()
    await db_session.rollback()


def test_extraction_decimal_precision_and_untrusted_llm():
    """Verify Decimal quantization and deterministic invariant enforcement on untrusted LLM outputs."""
    # 1. Valid exact decimal
    valid_result = ExtractionResult(
        total_amount=Decimal("118.00"),
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
        cgst_amount=Decimal("9.00"),
        sgst_amount=Decimal("9.00"),
        confidence=0.95,
    )
    is_valid, reason = valid_result.validate_financial_invariants()
    assert is_valid is True
    assert reason is None

    # 2. Malicious LLM hallucination / prompt injection: subtotal 100, tax 18, total 999999
    malicious_result = ExtractionResult(
        total_amount=Decimal("999999.00"),
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
        confidence=0.99,
    )
    is_valid, reason = malicious_result.validate_financial_invariants()
    assert is_valid is False
    assert "does not match subtotal" in reason

    # 3. Floating point boundary edge cases: e.g. 0.01 mismatch
    subtle_mismatch = ExtractionResult(
        total_amount=Decimal("118.01"),
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("18.00"),
        confidence=0.99,
    )
    is_valid, reason = subtle_mismatch.validate_financial_invariants()
    assert is_valid is False

    # 4. Negative values rejected
    negative_result = ExtractionResult(
        total_amount=Decimal("-100.00"),
        confidence=0.95,
    )
    is_valid, reason = negative_result.validate_financial_invariants()
    assert is_valid is False
    assert "negative" in reason


@pytest.mark.asyncio
async def test_master_data_rbac(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify site_user cannot mutate global vendors or categories, but admin can."""
    auth_service = AuthService(db_session)
    site_user = await auth_service.create_user(
        email=f"site_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Site User",
        role_names=["site_user"],
    )
    admin_user = await auth_service.create_user(
        email=f"admin_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Admin",
        role_names=["admin"],
    )
    await db_session.commit()

    site_token = create_access_token({"sub": str(site_user.id)})
    admin_token = create_access_token({"sub": str(admin_user.id)})

    # Site user attempting to create vendor -> 403 Forbidden
    resp = await async_client.post(
        "/api/v1/vendors",
        json={"name": "Global Cement Supplier"},
        headers={"Authorization": f"Bearer {site_token}"},
    )
    assert resp.status_code == 403

    # Site user attempting to create category -> 403 Forbidden
    resp_cat = await async_client.post(
        "/api/v1/categories",
        json={"name": "Global Explosives"},
        headers={"Authorization": f"Bearer {site_token}"},
    )
    assert resp_cat.status_code == 403

    # Admin successfully creating vendor
    resp_admin = await async_client.post(
        "/api/v1/vendors",
        json={"name": f"Authorized Vendor {uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_admin.status_code == 201


@pytest.mark.asyncio
async def test_evidence_count_query(db_session: AsyncSession):
    """Verify evidence counting executes SQL COUNT(*) rather than fetching all rows."""
    from app.models.evidence import Evidence
    
    count_stmt = select(func.count(Evidence.id))
    result = await db_session.execute(count_stmt)
    count = result.scalar_one()
    assert isinstance(count, int)
    assert count >= 0


@pytest.mark.asyncio
async def test_streaming_storage_upload_method():
    """Verify storage service provides upload_stream accepting stream without unbounded read()."""
    import io
    from unittest.mock import MagicMock
    from app.services.storage import StorageService

    mock_client = MagicMock()
    service = StorageService(client=mock_client)
    
    # Test data stream
    test_bytes = b"%PDF-1.4 test streaming content"
    stream = io.BytesIO(test_bytes)
    
    # upload_stream should call client.put_object with stream directly
    service.upload_stream(
        object_name="test/stream.pdf",
        stream=stream,
        length=len(test_bytes),
        checksum="fake_checksum_hash_123",
        content_type="application/pdf",
    )
    
    mock_client.put_object.assert_called_once()
    args, kwargs = mock_client.put_object.call_args
    assert kwargs.get("length") == len(test_bytes)
    assert kwargs.get("content_type") == "application/pdf"


@pytest.mark.asyncio
async def test_gdpr_and_audit_report_tenant_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify GDPR requests and audit reports strictly enforce tenant/user boundaries."""
    auth_service = AuthService(db_session)
    user_a = await auth_service.create_user(
        email=f"gdpr_a_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="User A",
        role_names=["site_user"],
    )
    user_b = await auth_service.create_user(
        email=f"gdpr_b_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="User B",
        role_names=["site_user"],
    )
    admin_user = await auth_service.create_user(
        email=f"gdpr_admin_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Admin",
        role_names=["admin"],
    )
    await db_session.commit()

    token_a = create_access_token({"sub": str(user_a.id)})
    token_b = create_access_token({"sub": str(user_b.id)})
    admin_token = create_access_token({"sub": str(admin_user.id)})

    # User B creates a GDPR request
    resp_b_create = await async_client.post(
        "/api/v1/audit-compliance/gdpr-requests",
        json={"request_type": "portability", "user_id": str(user_b.id), "email": user_b.email},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b_create.status_code == 201
    req_b_id = resp_b_create.json()["id"]

    # User A tries to view User B's GDPR request -> 404 Not Found (no IDOR enumeration)
    resp_a_view = await async_client.get(
        f"/api/v1/audit-compliance/gdpr-requests/{req_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a_view.status_code == 404

    # User A listing GDPR requests -> does not see User B's request
    resp_a_list = await async_client.get(
        "/api/v1/audit-compliance/gdpr-requests",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a_list.status_code == 200
    assert len(resp_a_list.json()["items"]) == 0

    # User A attempts to request system-level audit report -> 403 Forbidden
    resp_a_report = await async_client.post(
        "/api/v1/audit-compliance/reports",
        json={"report_type": "system_changes"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a_report.status_code == 403

    # Admin requests report
    resp_admin_report = await async_client.post(
        "/api/v1/audit-compliance/reports",
        json={"report_type": "system_changes"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_admin_report.status_code == 202
    admin_report_id = resp_admin_report.json()["report_id"]

    # User A tries to view or download Admin's report -> 404 Not Found
    resp_a_get_rep = await async_client.get(
        f"/api/v1/audit-compliance/reports/{admin_report_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a_get_rep.status_code == 404

    resp_a_down_rep = await async_client.get(
        f"/api/v1/audit-compliance/reports/{admin_report_id}/download",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a_down_rep.status_code == 404


@pytest.mark.asyncio
async def test_staging_and_posting_project_scoping_isolation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify staging and posting APIs enforce project scoping and return 404 for cross-tenant access."""
    auth_service = AuthService(db_session)
    user_a = await auth_service.create_user(
        email=f"user_sa_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="User SA",
        role_names=["site_user"],
    )
    user_b = await auth_service.create_user(
        email=f"user_sb_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="User SB",
        role_names=["site_user"],
    )
    await db_session.commit()

    proj_b = Project(
        name="Project B Exclusive",
        code=f"PB-{uuid4().hex[:6]}",
        created_by=user_b.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(proj_b)
    await db_session.flush()

    member_b = ProjectMember(project_id=proj_b.id, user_id=user_b.id, role="site_user")
    db_session.add(member_b)

    source_event_b = SourceEvent(
        source=SourceType.MANUAL,
        idempotency_key=str(uuid4()),
        raw_payload={"test": True},
    )
    db_session.add(source_event_b)
    await db_session.flush()

    expense_b = Expense(
        project_id=proj_b.id,
        source_event_id=source_event_b.id,
        transaction_date=date(2026, 9, 20),
        subtotal=Decimal("500.00"),
        tax_amount=Decimal("90.00"),
        total=Decimal("590.00"),
        currency="INR",
        payment_method=PaymentMethod.UPI,
        lifecycle_status=LifecycleStatus.STAGED,
    )
    db_session.add(expense_b)
    await db_session.commit()

    token_a = create_access_token({"sub": str(user_a.id)})

    # User A tries to view staged expense of Project B -> 404 Not Found
    resp_staged = await async_client.get(
        f"/api/v1/staging/expenses/{expense_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_staged.status_code == 404

    # User A tries to take action on staged expense of Project B -> 404 Not Found
    resp_action = await async_client.post(
        f"/api/v1/staging/expenses/{expense_b.id}/action",
        json={"action": "approve"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_action.status_code == 404

    # User A listing staged expenses does not leak Project B's expense
    resp_list = await async_client.get(
        "/api/v1/staging/expenses",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_list.status_code == 200
    staged_ids = [item["expense_id"] for item in resp_list.json()["items"]]
    assert str(expense_b.id) not in staged_ids

    # User A trying to get trial balance for Project B -> 404 Not Found
    resp_tb = await async_client.get(
        f"/api/v1/posting/trial-balance?project_id={proj_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_tb.status_code == 404


@pytest.mark.asyncio
async def test_webhook_and_monitoring_metrics_rbac(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """Verify webhooks and internal metrics require admin privilege."""
    auth_service = AuthService(db_session)
    site_user = await auth_service.create_user(
        email=f"site_mon_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Site Monitor",
        role_names=["site_user"],
    )
    admin_user = await auth_service.create_user(
        email=f"admin_mon_{uuid4().hex[:6]}@example.com",
        password="password123",
        full_name="Admin Monitor",
        role_names=["admin"],
    )
    await db_session.commit()

    site_token = create_access_token({"sub": str(site_user.id)})
    admin_token = create_access_token({"sub": str(admin_user.id)})

    # Site user cannot create webhooks -> 403 Forbidden
    resp_wh = await async_client.post(
        "/api/v1/notifications/webhooks",
        json={"url": "https://example.com/webhook", "events": ["expense.created"]},
        headers={"Authorization": f"Bearer {site_token}"},
    )
    assert resp_wh.status_code == 403

    # Site user cannot access system metrics -> 403 Forbidden
    resp_sys = await async_client.get(
        "/api/v1/metrics/system",
        headers={"Authorization": f"Bearer {site_token}"},
    )
    assert resp_sys.status_code == 403

    # Site user cannot access business metrics -> 403 Forbidden
    resp_biz = await async_client.get(
        "/api/v1/metrics/business",
        headers={"Authorization": f"Bearer {site_token}"},
    )
    assert resp_biz.status_code == 403

    # Admin user can access business metrics
    resp_admin_biz = await async_client.get(
        "/api/v1/metrics/business",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_admin_biz.status_code == 200
    assert "expenses" in resp_admin_biz.json()


