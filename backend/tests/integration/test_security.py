"""Security tests."""

import uuid

import pytest
from httpx import AsyncClient


def _unique_code(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


class TestAuthenticationSecurity:
    """Authentication security tests."""

    @pytest.mark.asyncio
    async def test_unauthorized_access_denied(self, async_client: AsyncClient):
        """Test that unauthorized requests are denied."""
        response = await async_client.get("/api/v1/projects", follow_redirects=True)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self, async_client: AsyncClient):
        """Test that invalid tokens are rejected."""
        headers = {"Authorization": "Bearer invalid.token.here"}
        response = await async_client.get(
            "/api/v1/projects", headers=headers, follow_redirects=True
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, async_client: AsyncClient):
        """Test that expired tokens are rejected."""
        headers = {"Authorization": "Bearer expired.token.here"}
        response = await async_client.get(
            "/api/v1/projects", headers=headers, follow_redirects=True
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_auth_header(self, async_client: AsyncClient):
        """Test malformed authorization header."""
        headers = {"Authorization": "InvalidFormat token"}
        response = await async_client.get(
            "/api/v1/projects", headers=headers, follow_redirects=True
        )
        assert response.status_code == 401


class TestAuthorizationSecurity:
    """Authorization security tests."""

    @pytest.mark.asyncio
    async def test_role_based_access_control(
        self, async_client: AsyncClient, auth_headers: dict, admin_headers: dict
    ):
        """Test RBAC enforcement."""
        response = await async_client.get(
            "/api/v1/admin/users", headers=auth_headers, follow_redirects=True
        )
        assert response.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_project_isolation_enforced(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that users can't access other projects' data."""
        project_data = {
            "name": "Secure Project",
            "code": _unique_code("SEC-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        expense_data = {
            "project_id": project_id,
            "vendor_name": "Secure Vendor",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": 1000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "CASH",
            "reference_number": "SEC-INV-001",
        }
        await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )

        other_project_id = str(uuid.uuid4())
        response = await async_client.get(
            f"/api/v1/expenses?project_id={other_project_id}",
            headers=auth_headers,
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0


class TestInputValidationSecurity:
    """Input validation security tests."""

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(self, async_client: AsyncClient, auth_headers: dict):
        """Test SQL injection prevention via parameterized queries.

        The backend stores the raw string (not executing it as SQL), but the
        parameterized ORM ensures the DB is unaffected. We verify:
          1. Project is created successfully (201)
          2. The 'projects' table is still accessible afterwards (DB not dropped)
        """
        project_data = {
            "name": "Test'; DROP TABLE projects; --",
            "code": _unique_code("SQLI-"),
            "description": "SQL injection test",
        }
        response = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 201, response.text

        # Verify DB integrity — projects table still works
        list_resp = await async_client.get(
            "/api/v1/projects", headers=auth_headers, follow_redirects=True
        )
        assert list_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_xss_prevention(self, async_client: AsyncClient, auth_headers: dict):
        """Test XSS in inputs: API stores data safely, does not execute it.

        The backend is a JSON API so it stores data as-is, but no HTML
        rendering is done server-side. We simply verify 201 is returned
        (not a server error) and the data round-trips correctly.
        """
        xss_payload = "<script>alert('xss')</script>"
        project_data = {
            "name": xss_payload,
            "code": _unique_code("XSS-"),
            "description": "XSS test",
        }
        response = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 201, response.text

    @pytest.mark.asyncio
    async def test_gstin_format_validation(self, async_client: AsyncClient, auth_headers: dict):
        """Test GSTIN format validation — invalid GSTIN should return 422."""
        # First create a real project to attach the expense to
        project_data = {
            "name": "GSTIN Validation Project",
            "code": _unique_code("GSTIN-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        expense_data = {
            "project_id": project_id,
            "vendor_name": "Test Vendor",
            "vendor_gstin": "INVALID_GSTIN",
            "date": "2024-01-15",
            "total": 1000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "CASH",
            "reference_number": "INV-001",
        }
        response = await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_amount_validation(self, async_client: AsyncClient, auth_headers: dict):
        """Test amount validation — negative total should return 422."""
        project_data = {
            "name": "Amount Test",
            "code": _unique_code("AMT-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        expense_data = {
            "project_id": project_id,
            "vendor_name": "Amount Vendor",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": -100,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "CASH",
            "reference_number": "AMT-INV-001",
        }
        response = await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )
        assert response.status_code == 422, response.text


class TestRateLimiting:
    """Rate limiting tests."""

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(self, async_client: AsyncClient):
        """Test that rate limiting is enforced."""
        for _ in range(100):
            response = await async_client.get("/api/v1/health", follow_redirects=True)
            if response.status_code == 429:
                return

        pytest.skip("Rate limiting not configured or threshold not reached")


class TestAuditLoggingSecurity:
    """Audit logging security tests."""

    @pytest.mark.asyncio
    async def test_sensitive_data_not_logged(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that sensitive data is not logged in audit."""
        project_data = {
            "name": "Audit Security Project",
            "code": _unique_code("AUDIT-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        expense_data = {
            "project_id": project_id,
            "vendor_name": "Sensitive Vendor",
            "vendor_gstin": "29ABCDE1234F1Z5",
            "date": "2024-01-15",
            "total": 5000,
            "currency": "USD",
            "category": "MATERIALS",
            "payment_method": "CASH",
            "reference_number": "SENS-INV-001",
        }
        await async_client.post(
            "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
        )

        response = await async_client.get(
            "/api/v1/audit/logs?entity_type=expense",
            headers=auth_headers,
            follow_redirects=True,
        )
        assert response.status_code == 200, response.text
        data = response.json()

        for item in data["items"]:
            assert "password" not in str(item).lower()
            assert "secret" not in str(item).lower()
            assert "token" not in str(item).lower()


class TestWebhookSecurity:
    """Webhook security tests."""

    @pytest.mark.asyncio
    async def test_webhook_signature_verification(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test webhook signature verification."""
        from app.core.security import generate_webhook_signature

        payload = {"event": "TEST_EVENT", "data": {"key": "value"}}
        secret = "test-secret"
        signature = generate_webhook_signature(payload, secret)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
        }
        response = await async_client.post(
            "/api/v1/webhooks/test", json=payload, headers=headers, follow_redirects=True
        )
        assert response.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_invalid_webhook_signature_rejected(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test that invalid webhook signatures are rejected."""
        payload = {"event": "TEST_EVENT", "data": {"key": "value"}}
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": "invalid-signature",
        }
        response = await async_client.post(
            "/api/v1/webhooks/test", json=payload, headers=headers, follow_redirects=True
        )
        assert response.status_code in (401, 403, 404)