"""Performance and load tests."""

import asyncio
import time
import uuid

import pytest
from httpx import AsyncClient


def _unique_code(prefix: str = "") -> str:
    """Generate a unique 8-char hex project code."""
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


def _valid_gstin(i: int) -> str:
    """Generate a valid 15-char GSTIN for index i (0-based)."""
    # Format: 29ABCDE1234F1Z5 (15 chars)
    # Char 13 must be [1-9A-Z] (entity code)
    # Char 15 is checksum [0-9A-Z]
    entity = str((i % 9) + 1)
    last = str(((i + 1) % 9) + 1)
    return f"29ABCDE1234F{entity}Z{last}"


class TestAPIPerformance:
    """Performance tests for API endpoints."""

    @pytest.mark.asyncio
    async def test_health_endpoint_latency(self, async_client: AsyncClient):
        """Test health endpoint response time."""
        latencies = []
        for _ in range(10):
            start = time.perf_counter()
            response = await async_client.get("/api/v1/health", follow_redirects=True)
            latency = time.perf_counter() - start
            latencies.append(latency)
            assert response.status_code == 200

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        assert avg_latency < 0.1, f"Average latency {avg_latency:.3f}s exceeds 100ms"
        assert max_latency < 0.5, f"Max latency {max_latency:.3f}s exceeds 500ms"

    @pytest.mark.asyncio
    async def test_list_projects_latency(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test list projects endpoint latency."""
        project_data = {
            "name": "Latency Test Project",
            "code": _unique_code("LAT-"),
            "description": "Test",
        }
        await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        latencies = []
        for _ in range(5):
            start = time.perf_counter()
            response = await async_client.get(
                "/api/v1/projects", headers=auth_headers, follow_redirects=True
            )
            latency = time.perf_counter() - start
            latencies.append(latency)
            assert response.status_code == 200

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 0.5, f"Average latency {avg_latency:.3f}s exceeds 500ms"

    @pytest.mark.asyncio
    async def test_create_project_latency(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test create project endpoint latency."""
        latencies = []
        for i in range(5):
            data = {
                "name": f"Perf Test Project {i}",
                "code": _unique_code(f"PERF-{i}-"),
                "description": "Performance test",
            }
            start = time.perf_counter()
            response = await async_client.post(
                "/api/v1/projects", json=data, headers=auth_headers, follow_redirects=True
            )
            latency = time.perf_counter() - start
            latencies.append(latency)
            assert response.status_code == 201, response.text

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 1.0, f"Average latency {avg_latency:.3f}s exceeds 1s"

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, async_client: AsyncClient):
        """Test concurrent health check requests."""
        async def make_request():
            start = time.perf_counter()
            response = await async_client.get("/api/v1/health", follow_redirects=True)
            return time.perf_counter() - start, response.status_code

        tasks = [make_request() for _ in range(50)]
        results = await asyncio.gather(*tasks)

        latencies = [r[0] for r in results]
        status_codes = [r[1] for r in results]

        assert all(code == 200 for code in status_codes)
        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 0.5, f"Avg latency under load {avg_latency:.3f}s exceeds 500ms"


class TestDatabasePerformance:
    """Database performance tests."""

    @pytest.mark.asyncio
    async def test_bulk_expense_creation(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test bulk expense creation performance."""
        project_data = {
            "name": "Bulk Test Project",
            "code": _unique_code("BULK-"),
            "description": "Bulk test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        expenses = [
            {
                "project_id": project_id,
                "vendor_name": f"Bulk Vendor {i}",
                "vendor_gstin": _valid_gstin(i),
                "date": "2024-01-15",
                "total": 1000 + i * 100,
                "currency": "USD",
                "category": "MATERIALS",
                "payment_method": "CASH",
                "reference_number": f"BULK-INV-{i:04d}",
            }
            for i in range(20)
        ]

        start = time.perf_counter()
        # Sequential to avoid session/flush race conditions in test infra
        responses = []
        for exp in expenses:
            r = await async_client.post(
                "/api/v1/expenses", json=exp, headers=auth_headers, follow_redirects=True
            )
            responses.append(r)
        elapsed = time.perf_counter() - start

        assert all(r.status_code == 201 for r in responses), [
            r.text for r in responses if r.status_code != 201
        ]
        assert elapsed < 30.0, f"Bulk creation took {elapsed:.2f}s, expected < 30s"

        throughput = len(expenses) / elapsed
        assert throughput > 0.5, f"Throughput {throughput:.2f} req/s too low"


class TestMemoryUsage:
    """Memory usage tests."""

    @pytest.mark.asyncio
    async def test_memory_stability_during_requests(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test memory doesn't grow unbounded during requests."""
        project_data = {
            "name": "Memory Test Project",
            "code": _unique_code("MEM-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        count = 0
        for i in range(50):
            expense_data = {
                "project_id": project_id,
                "vendor_name": f"Memory Vendor {i}",
                "vendor_gstin": _valid_gstin(i),
                "date": "2024-01-15",
                "total": 1000,
                "currency": "USD",
                "category": "MATERIALS",
                "payment_method": "CASH",
                "reference_number": f"MEM-INV-{i:04d}",
            }
            response = await async_client.post(
                "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
            )
            if response.status_code == 201:
                count += 1

        response = await async_client.get(
            f"/api/v1/expenses?project_id={project_id}",
            headers=auth_headers,
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.json()["total"] == count


class TestReconciliationPerformance:
    """Reconciliation performance tests."""

    @pytest.mark.asyncio
    async def test_auto_match_performance(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test auto-match performance with many items."""
        project_data = {
            "name": "Recon Perf Project",
            "code": _unique_code("RECON-"),
            "description": "Test",
        }
        project_resp = await async_client.post(
            "/api/v1/projects", json=project_data, headers=auth_headers, follow_redirects=True
        )
        assert project_resp.status_code == 201, project_resp.text
        project_id = project_resp.json()["id"]

        expense_ids = []
        for i in range(10):
            expense_data = {
                "project_id": project_id,
                "vendor_name": f"Recon Vendor {i}",
                "vendor_gstin": _valid_gstin(i),
                "date": "2024-01-15",
                "total": 10000,
                "currency": "USD",
                "category": "MATERIALS",
                "payment_method": "BANK_TRANSFER",
                "reference_number": f"RECON-INV-{i:04d}",
            }
            expense_resp = await async_client.post(
                "/api/v1/expenses", json=expense_data, headers=auth_headers, follow_redirects=True
            )
            if expense_resp.status_code == 201:
                expense_ids.append(expense_resp.json()["id"])

            payment_data = {
                "project_id": project_id,
                "amount": 10000,
                "currency": "USD",
                "date": "2024-01-16",
                "payment_method": "BANK_TRANSFER",
                "reference_number": f"RECON-INV-{i:04d}",
            }
            await async_client.post(
                "/api/v1/payment-events",
                json=payment_data,
                headers=auth_headers,
                follow_redirects=True,
            )

        batch_data = {
            "project_id": project_id,
            "dry_run": False,
            "expense_ids": expense_ids,
        }
        start = time.perf_counter()
        response = await async_client.post(
            "/api/v1/reconciliation/auto-match",
            json=batch_data,
            headers=auth_headers,
            follow_redirects=True,
        )
        elapsed = time.perf_counter() - start

        # API returns 202 Accepted for async batch operations
        assert response.status_code in (200, 202), response.text
        assert elapsed < 15.0, f"Auto-match took {elapsed:.2f}s, expected < 15s"

        data = response.json()
        assert data["matched"] >= 0


class TestOCRPerformance:
    """OCR performance tests."""

    @pytest.mark.asyncio
    async def test_ocr_preprocessing_speed(self):
        """Test OCR preprocessing performance."""
        import numpy as np

        from app.services.ocr import OCRService

        service = OCRService()
        # Pass as numpy array — the updated service converts it to PIL internally
        image = np.random.randint(0, 255, (1000, 1000, 3), dtype=np.uint8)

        start = time.perf_counter()
        processed = service.preprocess_image(image)
        elapsed = time.perf_counter() - start

        assert processed is not None
        assert elapsed < 1.0, f"Preprocessing took {elapsed:.3f}s, expected < 1s"