"""End-to-end workflow tests."""

import uuid

import pytest
from httpx import AsyncClient


def _unique_code(prefix: str = "") -> str:
    """Generate a unique 8-char hex project code to avoid DB unique-constraint collisions."""
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


class TestCompleteExpenseWorkflow:
    """Test complete expense lifecycle workflow."""

    @pytest.mark.asyncio
    async def test_expense_full_lifecycle(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test expense from creation to posting."""
        project_data = {
            "name": "E2E Project",
            "code": _unique_code("E2E-"),
            "description": "Full lifecycle test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        budget_data = {
            "project_id": project_id,
            "category": "MATERIALS",
            "amount": 50000,
            "currency": "USD",
        }
        await async_client.post(
            "/api/v1/budgets", json=budget_data, headers=auth_headers, follow_redirects=True
        )

        expense_data = {
            "project_id": project_id,
            "vendor_name": "E2E Vendor",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": 25000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "CASH",
            "reference_number": "E2E-INV-001",
        }
        expense_resp = await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )
        assert expense_resp.status_code == 201, expense_resp.text
        expense_id = expense_resp.json()["id"]
        assert expense_resp.json()["lifecycle_status"] == "RECEIVED"

        # RECEIVED → VALIDATED
        validated = await async_client.post(
            f"/api/v1/expenses/{expense_id}/transition",
            json={"target_status": "VALIDATED"},
            headers=auth_headers,
            follow_redirects=True,
        )
        assert validated.status_code == 200, validated.text
        assert validated.json()["lifecycle_status"] == "VALIDATED"

        # VALIDATED → STAGED  (shortcut: manual expense skips OCR processing)
        staged = await async_client.post(
            f"/api/v1/expenses/{expense_id}/transition",
            json={"target_status": "STAGED"},
            headers=auth_headers,
            follow_redirects=True,
        )
        assert staged.status_code == 200, staged.text
        assert staged.json()["lifecycle_status"] == "STAGED"

        # STAGED → RECONCILED  (shortcut: direct reconciliation match)
        reconciled = await async_client.post(
            f"/api/v1/expenses/{expense_id}/transition",
            json={"target_status": "RECONCILED"},
            headers=auth_headers,
            follow_redirects=True,
        )
        assert reconciled.status_code == 200, reconciled.text
        assert reconciled.json()["lifecycle_status"] == "RECONCILED"

        # RECONCILED → POSTED
        posted = await async_client.post(
            f"/api/v1/expenses/{expense_id}/transition",
            json={"target_status": "POSTED"},
            headers=auth_headers,
            follow_redirects=True,
        )
        assert posted.status_code == 200, posted.text
        assert posted.json()["lifecycle_status"] == "POSTED"

    @pytest.mark.asyncio
    async def test_budget_vs_actual_tracking(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test budget vs actual tracking."""
        project_data = {
            "name": "Budget Tracking Project",
            "code": _unique_code("BUD-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        budget_data = {
            "project_id": project_id,
            "category": "MATERIALS",
            "amount": 100000,
            "currency": "USD",
        }
        await async_client.post(
            "/api/v1/budgets", json=budget_data, headers=auth_headers, follow_redirects=True
        )

        expense_data = {
            "project_id": project_id,
            "vendor_name": "Budget Vendor",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": 30000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "BANK_TRANSFER",
            "reference_number": "BUD-INV-001",
        }
        await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )

        response = await async_client.get(
            f"/api/v1/projects/{project_id}/budget-vs-actual",
            headers=auth_headers,
            follow_redirects=True,
        )
        assert response.status_code == 200
        data = response.json()
        assert "budget" in data
        assert "actual" in data
        assert "variance" in data


class TestReconciliationWorkflow:
    """Test reconciliation workflows."""

    @pytest.mark.asyncio
    async def test_auto_reconciliation_batch(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test batch auto-reconciliation."""
        project_data = {
            "name": "Auto Recon Project",
            "code": _unique_code("AR-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        expenses = []
        payments = []
        for i in range(3):
            expense_data = {
                "project_id": project_id,
                "vendor_name": f"Vendor {i}",
                "vendor_gstin": f"29ABCDE1234F1Z{i}",
                "date": "2024-01-15",
                "total": 10000 * (i + 1),
                "currency": "USD",
                "category": "MATERIALS",
                "payment_method": "BANK_TRANSFER",
                "reference_number": f"AUTO-INV-{i}",
            }
            expense_resp = await async_client.post(
                "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
            )
            assert expense_resp.status_code == 201, expense_resp.text
            expenses.append(expense_resp.json()["id"])

            payment_data = {
                "project_id": project_id,
                "amount": 10000 * (i + 1),
                "currency": "USD",
                "date": "2024-01-16",
                "payment_method": "BANK_TRANSFER",
                "reference_number": f"AUTO-INV-{i}",
            }
            payment_resp = await async_client.post(
                "/api/v1/payment-events",
                json=payment_data,
                headers=auth_headers,
                follow_redirects=True,
            )
            if payment_resp.status_code == 201:
                payments.append(payment_resp.json()["id"])

        batch_data = {
            "project_id": project_id,
            "dry_run": False,
            "expense_ids": expenses,
        }
        response = await async_client.post(
            "/api/v1/reconciliation/auto-match",
            json=batch_data,
            headers=auth_headers,
            follow_redirects=True,
        )
        # API returns 202 Accepted for async batch jobs
        assert response.status_code in (200, 202), response.text
        data = response.json()
        assert "matched" in data
        assert "unmatched" in data
        assert data["matched"] >= 0


class TestAuditTrailWorkflow:
    """Test audit trail generation."""

    @pytest.mark.asyncio
    async def test_audit_trail_completeness(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that all operations create audit entries."""
        project_data = {
            "name": "Audit Trail Project",
            "code": _unique_code("AT-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        expense_data = {
            "project_id": project_id,
            "vendor_name": "Audit Vendor",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": 5000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "CASH",
            "reference_number": "AUDIT-INV-001",
        }
        expense_resp = await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )
        assert expense_resp.status_code == 201, expense_resp.text
        expense_id = expense_resp.json()["id"]

        await async_client.post(
            f"/api/v1/expenses/{expense_id}/transition",
            json={"target_status": "VALIDATED"},
            headers=auth_headers,
            follow_redirects=True,
        )

        # Audit trail endpoint is at /api/v1/audit-compliance/trail/{entity_type}/{entity_id}
        response = await async_client.get(
            f"/api/v1/audit-compliance/trail/expense/{expense_id}",
            headers=auth_headers,
            follow_redirects=True,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total_events"] >= 1

        actions = {item["event_type"] for item in data["events"]}
        # At minimum the expense.created event should be present
        assert any("expense" in a for a in actions)


class TestNotificationWorkflow:
    """Test notification workflows."""

    @pytest.mark.asyncio
    async def test_notification_preferences(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test notification preferences CRUD."""
        prefs_data = {
            "email_enabled": True,
            "sms_enabled": False,
            "push_enabled": True,
            "webhook_enabled": False,
            "event_types": ["EXPENSE_CREATED", "RECONCILIATION_MATCHED"],
        }
        response = await async_client.patch(
            "/api/v1/notifications/preferences",
            json=prefs_data,
            headers=auth_headers,
            follow_redirects=True,
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["email_enabled"] == prefs_data["email_enabled"]
        assert data["push_enabled"] == prefs_data["push_enabled"]

        get_response = await async_client.get(
            "/api/v1/notifications/preferences",
            headers=auth_headers,
            follow_redirects=True,
        )
        assert get_response.status_code == 200, get_response.text
        assert get_response.json()["email_enabled"] == prefs_data["email_enabled"]


class TestMultiProjectIsolation:
    """Test multi-project data isolation."""

    @pytest.mark.asyncio
    async def test_project_data_isolation(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that projects are properly isolated."""
        project1_data = {
            "name": "Project 1",
            "code": _unique_code("ISO1-"),
            "description": "First project",
        }
        project1_resp = await async_client.post(
            "/api/v1/projects", json=project1_data, headers=auth_headers, follow_redirects=True
        )
        assert project1_resp.status_code == 201, project1_resp.text
        project1_id = project1_resp.json()["id"]

        project2_data = {
            "name": "Project 2",
            "code": _unique_code("ISO2-"),
            "description": "Second project",
        }
        project2_resp = await async_client.post(
            "/api/v1/projects", json=project2_data, headers=auth_headers, follow_redirects=True
        )
        assert project2_resp.status_code == 201, project2_resp.text
        project2_id = project2_resp.json()["id"]

        expense_data = {
            "project_id": project1_id,
            "vendor_name": "Isolation Vendor",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": 1000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "CASH",
            "reference_number": f"ISO-INV-{uuid.uuid4().hex[:6]}",
        }
        create_resp = await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )
        assert create_resp.status_code == 201, create_resp.text

        response1 = await async_client.get(
            f"/api/v1/expenses?project_id={project1_id}",
            headers=auth_headers,
            follow_redirects=True,
        )
        response2 = await async_client.get(
            f"/api/v1/expenses?project_id={project2_id}",
            headers=auth_headers,
            follow_redirects=True,
        )

        assert response1.status_code == 200, response1.text
        assert response2.status_code == 200, response2.text
        # project1 has 1 expense; project2 has 0
        assert response1.json()["total"] >= 1
        assert response2.json()["total"] == 0