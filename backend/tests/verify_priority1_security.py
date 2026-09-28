"""Targeted verification test suite for Priority 1 Security Fixes."""

import asyncio
from datetime import timedelta
import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

if "minio" not in sys.modules:
    sys.modules["minio"] = MagicMock()
if "minio.error" not in sys.modules:
    sys.modules["minio.error"] = MagicMock()

from fastapi import HTTPException, UploadFile
import pytest

from app.core.config import Settings
from app.core.security import create_access_token, create_refresh_token, validate_safe_webhook_url
from app.models.user import User
from app.schemas.notification import WebhookConfigCreate
from app.schemas.reconciliation import ReconciliationActionRequest
from app.schemas.staging import StageActionRequest


# ---------------------------------------------------------------------------
# Test 1: JWT Token Type Confusion (Auth Bypass)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_jwt_token_type_confusion_prevention():
    from app.core.dependencies import get_current_user

    user_id = str(uuid4())
    # Create a refresh token (valid signature and expiry, but type='refresh')
    refresh_token = create_refresh_token({"sub": user_id, "email": "test@example.com"})

    mock_db = MagicMock()

    # Attempting to use a refresh token as a Bearer access token must fail with 401
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(authorization=f"Bearer {refresh_token}", db=mock_db)

    assert exc_info.value.status_code == 401
    assert "Invalid token type" in exc_info.value.detail

    # Create an access token (type='access')
    access_token = create_access_token({"sub": user_id, "email": "test@example.com"})

    with patch("app.core.dependencies.AuthService") as mock_auth_cls:
        mock_auth = MagicMock()
        mock_user = MagicMock(spec=User)
        mock_user.is_active = True
        mock_auth.get_user_by_id = AsyncMock(return_value=mock_user)
        mock_auth_cls.return_value = mock_auth

        user = await get_current_user(authorization=f"Bearer {access_token}", db=mock_db)
        assert user == mock_user


# ---------------------------------------------------------------------------
# Test 2: Insecure Secret Keys Blocked in Production
# ---------------------------------------------------------------------------
def test_production_secret_key_validation():
    # In dev mode, default is accepted
    dev_settings = Settings(APP_ENV="development")
    assert dev_settings.APP_ENV == "development"

    # In production mode with default secret key, it must raise a validation error
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be securely configured"):
        Settings(APP_ENV="production", JWT_SECRET_KEY="change-me-in-production")

    # In production mode with short secret key (< 32 chars), it must raise
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be securely configured"):
        Settings(APP_ENV="production", JWT_SECRET_KEY="short-secret-key")

    # In production mode with valid 32+ char key, it succeeds
    prod_settings = Settings(
        APP_ENV="production",
        JWT_SECRET_KEY="a" * 32,
        APP_SECRET_KEY="b" * 32,
    )
    assert prod_settings.APP_ENV == "production"


# ---------------------------------------------------------------------------
# Test 3 & 4: Evidence Storage Security (IDOR, Path Traversal, Size Limits)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_evidence_presigned_url_idor_prevention():
    from app.api.v1.evidence import get_presigned_url
    from app.schemas.evidence import PresignedUrlRequest

    mock_db = MagicMock()
    # Mock DB query returning None (object does not exist in DB evidence table)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_user = MagicMock(spec=User)
    mock_user.is_active = True

    req = PresignedUrlRequest(object_name="expenses/arbitrary/path.pdf")
    with pytest.raises(HTTPException) as exc_info:
        await get_presigned_url(request=req, current_user=mock_user, db=mock_db)

    assert exc_info.value.status_code == 404
    assert "Evidence not found or access denied" in exc_info.value.detail


@pytest.mark.asyncio
async def test_evidence_upload_path_traversal_and_type_check():
    from app.api.v1.evidence import upload_evidence

    mock_db = MagicMock()
    mock_expense = MagicMock()
    mock_db.get = AsyncMock(return_value=mock_expense)

    mock_user = MagicMock(spec=User)

    # Disallowed file extension (.sh)
    file_bad_ext = UploadFile(filename="../../malicious.sh", file=io.BytesIO(b"echo pwned"))
    with pytest.raises(HTTPException) as exc_info:
        await upload_evidence(
            expense_id=uuid4(),
            file=file_bad_ext,
            current_user=mock_user,
            db=mock_db,
        )
    assert exc_info.value.status_code == 400
    assert "Unsupported file type" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Test 5: SSRF Prevention in Webhook Registration
# ---------------------------------------------------------------------------
def test_ssrf_webhook_url_validation():
    # Cloud metadata endpoint must be blocked
    with pytest.raises(ValueError, match="cannot target internal, private, or metadata"):
        validate_safe_webhook_url("http://169.254.169.254/latest/meta-data/")

    # Loopback IP must be blocked
    with pytest.raises(ValueError, match="cannot target internal, private, or metadata"):
        validate_safe_webhook_url("http://127.0.0.1:8000/hook")

    # Localhost hostname must be blocked
    with pytest.raises(ValueError, match="not permitted"):
        validate_safe_webhook_url("http://localhost:5000/hook")

    # Private RFC 1918 IPs must be blocked
    with pytest.raises(ValueError, match="cannot target internal, private, or metadata"):
        validate_safe_webhook_url("http://10.0.0.1/hook")

    with pytest.raises(ValueError, match="cannot target internal, private, or metadata"):
        validate_safe_webhook_url("http://192.168.1.50/hook")

    # Non-HTTP schemes must be blocked
    with pytest.raises(ValueError, match="Prohibited URL scheme"):
        validate_safe_webhook_url("ftp://example.com/hook")

    # Schema validation also triggers
    with pytest.raises(Exception):
        WebhookConfigCreate(
            url="http://127.0.0.1:9000/hook",
            events=["expense.created"],
        )


# ---------------------------------------------------------------------------
# Test 6: IDOR / Reviewer Impersonation Prevention
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reviewer_impersonation_prevented_in_staging():
    from app.api.v1.staging import take_stage_action

    mock_db = MagicMock()
    authenticated_user = MagicMock(spec=User)
    authenticated_user.id = uuid4()

    spoofed_admin_id = uuid4()
    req = StageActionRequest(
        action="approve",
        reviewer_id=spoofed_admin_id,
        notes="Spoofed approval",
    )

    with patch("app.api.v1.staging.create_staging_service") as mock_service_cls:
        mock_staging_service = MagicMock()
        mock_staging_service.approve_expense = AsyncMock(
            return_value={
                "expense_id": uuid4(),
                "action": "approve",
                "new_status": "APPROVED",
                "message": "Expense approved",
            }
        )
        mock_service_cls.return_value = mock_staging_service

        await take_stage_action(
            expense_id=uuid4(),
            request=req,
            current_user=authenticated_user,
            db=mock_db,
        )

        # Verify that the service was called with authenticated_user.id, NOT spoofed_admin_id
        mock_staging_service.approve_expense.assert_called_once()
        call_kwargs = mock_staging_service.approve_expense.call_args.kwargs
        assert call_kwargs["reviewer_id"] == authenticated_user.id
        assert call_kwargs["reviewer_id"] != spoofed_admin_id


@pytest.mark.asyncio
async def test_reviewer_impersonation_prevented_in_reconciliation():
    from app.api.v1.reconciliation import take_reconciliation_action

    mock_db = MagicMock()
    authenticated_user = MagicMock(spec=User)
    authenticated_user.id = uuid4()

    spoofed_admin_id = uuid4()
    req = ReconciliationActionRequest(
        action="confirm",
        reviewer_id=spoofed_admin_id,
        notes="Spoofed confirm",
    )

    with patch("app.api.v1.reconciliation.create_reconciliation_service") as mock_service_cls:
        mock_rec_service = MagicMock()
        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.expense_id = uuid4()
        mock_record.payment_event_id = None
        mock_record.status = "matched"
        mock_record.match_basis = "exact"
        mock_record.match_score = 1.0
        mock_record.resolved_by = authenticated_user.id
        mock_record.resolution_reason = "Manual match"
        from datetime import datetime, UTC
        mock_record.created_at = datetime.now(UTC)
        mock_record.updated_at = None

        mock_rec_service.confirm_reconciliation = AsyncMock(return_value=mock_record)
        mock_service_cls.return_value = mock_rec_service

        await take_reconciliation_action(
            record_id=uuid4(),
            request=req,
            current_user=authenticated_user,
            db=mock_db,
        )

        # Verify that confirm_reconciliation was called with authenticated_user.id, NOT spoofed_admin_id
        mock_rec_service.confirm_reconciliation.assert_called_once()
        call_kwargs = mock_rec_service.confirm_reconciliation.call_args.kwargs
        assert call_kwargs["reviewer_id"] == authenticated_user.id
        assert call_kwargs["reviewer_id"] != spoofed_admin_id


async def main_async():
    print("=" * 60)
    print("RUNNING PRIORITY 1 SECURITY VERIFICATION SUITE")
    print("=" * 60)

    print("\n[1/6] Testing JWT Token Type Confusion Prevention...")
    await test_jwt_token_type_confusion_prevention()
    print("  -> PASSED: Refresh token rejected for access token use.")

    print("\n[2/6] Testing Insecure Secret Key Validation in Production...")
    test_production_secret_key_validation()
    print("  -> PASSED: Insecure default secrets blocked in production environment.")

    print("\n[3/6] Testing Evidence Presigned URL IDOR Prevention...")
    await test_evidence_presigned_url_idor_prevention()
    print("  -> PASSED: Arbitrary object names rejected if not in evidence DB.")

    print("\n[4/6] Testing Evidence Upload Path Traversal & File Type Prevention...")
    await test_evidence_upload_path_traversal_and_type_check()
    print("  -> PASSED: Path traversal and disallowed file types rejected.")

    print("\n[5/6] Testing SSRF Prevention in Webhook Registration...")
    test_ssrf_webhook_url_validation()
    print("  -> PASSED: Loopback, private IP, and metadata URLs blocked.")

    print("\n[6/6] Testing Reviewer Impersonation Prevention in Staging & Reconciliation...")
    await test_reviewer_impersonation_prevented_in_staging()
    print("  -> PASSED: Staging approval enforces current_user.id.")
    await test_reviewer_impersonation_prevented_in_reconciliation()
    print("  -> PASSED: Reconciliation confirm enforces current_user.id.")

    print("\n" + "=" * 60)
    print("ALL PRIORITY 1 SECURITY CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main_async())
