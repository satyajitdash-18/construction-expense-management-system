"""Integration tests for API endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


class TestProjectsAPI:
    """Integration tests for projects API."""

    @pytest.mark.asyncio
    async def test_create_project(self, async_client: AsyncClient, auth_headers: dict):
        """Test creating a project."""
        project_data = {
            "name": "Test Project",
            "code": f"TEST-PROJ-{uuid4().hex[:6]}",
            "description": "Integration test project",
            "location": "Test Location",
            "status": "active",
        }
        response = await async_client.post(
            "/api/v1/projects",
            json=project_data,
            headers=auth_headers,
            follow_redirects=True,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == project_data["name"]
        assert data["code"] == project_data["code"]
        assert data["status"] == "active"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_projects(self, async_client: AsyncClient, auth_headers: dict):
        """Test listing projects."""
        response = await async_client.get(
            "/api/v1/projects", headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data or isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_project(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting a single project."""
        project_data = {"name": "Test Project 2", "code": f"TEST-PROJ-{uuid4().hex[:6]}", "description": "Test"}
        create_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        project_id = create_resp.json()["id"]

        response = await async_client.get(
            f"/api/v1/projects/{project_id}", headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == project_data["name"]


class TestBudgetsAPI:
    """Integration tests for budgets API."""

    @pytest.mark.asyncio
    async def test_create_budget(self, async_client: AsyncClient, auth_headers: dict):
        """Test creating a budget for a project."""
        project_data = {"name": "Budget Project", "code": f"BUD-PROJ-{uuid4().hex[:6]}", "description": "Test"}
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        project_id = project_resp.json()["id"]

        budget_data = {
            "amount": 100000,
            "currency": "USD",
        }
        response = await async_client.post(
            f"/api/v1/projects/{project_id}/budgets", json=budget_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 201
        data = response.json()
        assert data["project_id"] == project_id
        assert data["amount"] == budget_data["amount"]



class TestExpensesAPI:
    """Integration tests for expenses API."""

    @pytest.mark.asyncio
    async def test_create_expense(self, async_client: AsyncClient, auth_headers: dict):
        """Test creating an expense."""
        project_data = {"name": "Expense Project", "code": f"EXP-PROJ-{uuid4().hex[:6]}", "description": "Test"}
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        project_id = project_resp.json()["id"]

        expense_data = {
            "project_id": project_id,
            "vendor_name": "Test Vendor",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": 5000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "CASH",
            "reference_number": "INV-001",
        }
        response = await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 201
        data = response.json()
        assert data["vendor_name"] == expense_data["vendor_name"]
        assert float(data["total"]) == float(expense_data["total"])
        assert data["lifecycle_status"] == "RECEIVED"


    @pytest.mark.asyncio
    async def test_list_expenses(self, async_client: AsyncClient, auth_headers: dict):
        """Test listing expenses with filters."""
        response = await async_client.get(
            "/api/v1/expenses?status=RECEIVED", headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_manual_reconciliation(self, async_client: AsyncClient, auth_headers: dict):
        """Test manual reconciliation of expense and payment."""
        project_data = {"name": "Recon Project", "code": f"RECON-PROJ-{uuid4().hex[:6]}", "description": "Test"}
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        project_id = project_resp.json()["id"]


        expense_data = {
            "project_id": project_id,
            "vendor_name": "Vendor A",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": 10000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "BANK_TRANSFER",
            "reference_number": "INV-002",
        }
        expense_resp = await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )
        expense_id = expense_resp.json()["id"]

        payment_data = {
            "project_id": project_id,
            "amount": 10000,
            "currency": "USD",
            "date": "2024-01-16",
            "payment_method": "BANK_TRANSFER",
            "reference_number": "PAY-001",
        }
        payment_resp = await async_client.post(
            "/api/v1/payment-events", json=payment_data, headers=auth_headers, follow_redirects=True
        )
        payment_id = payment_resp.json()["id"]

        recon_data = {
            "expense_id": expense_id,
            "payment_event_id": payment_id,
            "match_basis": "MANUAL",
            "notes": "Manual reconciliation for testing",
        }
        response = await async_client.post(
            "/api/v1/reconciliation", json=recon_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 201
        data = response.json()
        assert data["expense_id"] == expense_id
        assert data["payment_event_id"] == payment_id
        assert data["status"] == "MATCHED"


class TestVendorsAPI:
    """Integration tests for vendors API."""

    @pytest.mark.asyncio
    async def test_create_vendor(self, async_client: AsyncClient, auth_headers: dict):
        """Test creating a vendor."""
        vendor_data = {
            "name": f"Integration Vendor {uuid4().hex[:6]}",
            "gstin": "29ABCDE1234F1Z5",
            "email": "vendor@test.com",
            "phone": "+1234567890",
            "address": "123 Vendor St",
            "city": "Test City",
            "state": "Test State",
            "postal_code": "12345",
            "country": "USA",
        }
        response = await async_client.post(
            "/api/v1/vendors", json=vendor_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == vendor_data["name"]
        assert data["gstin"] == vendor_data["gstin"]


class TestCategoriesAPI:
    """Integration tests for categories API."""

    @pytest.mark.asyncio
    async def test_list_categories(self, async_client: AsyncClient, auth_headers: dict):
        """Test listing expense categories."""
        await async_client.post(
            "/api/v1/categories",
            json={"name": f"Materials {uuid4().hex[:6]}"},
            headers=auth_headers,
            follow_redirects=True,
        )
        response = await async_client.get(
            "/api/v1/categories", headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0



class TestAuditComplianceAPI:
    """Integration tests for audit compliance API."""

    @pytest.mark.asyncio
    async def test_get_audit_logs(self, async_client: AsyncClient, auth_headers: dict):
        """Test retrieving audit logs."""
        response = await async_client.get(
            "/api/v1/audit-compliance/trail/expense/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
            follow_redirects=True,
        )
        assert response.status_code in (200, 404)
        data = response.json()
        assert "events" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_generate_audit_report(self, async_client: AsyncClient, auth_headers: dict):
        """Test generating an audit report."""
        report_data = {
            "report_type": "EXPENSE_SUMMARY",
            "format": "JSON",
            "filters": {"date_from": "2024-01-01", "date_to": "2024-12-31"},
        }
        response = await async_client.post(
            "/api/v1/audit-compliance/reports", json=report_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 202
        data = response.json()
        assert "report_id" in data
        assert data["status"] == "generating"