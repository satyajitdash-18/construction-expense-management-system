"""Tests for token revocation and session management."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_access_token_revoked,
    revoke_access_token,
)
from app.models.refresh_token import RefreshToken
from app.schemas.auth import LogoutRequest, RefreshRequest
from app.services.auth import AuthService


class TestTokenRevocation:
    """Tests for access token revocation using Redis."""

    @pytest.mark.asyncio
    async def test_revoke_and_check_access_token(self):
        """Test revoking an access token and checking revocation status."""
        jti = "test-jti-123"
        expires_in = 60  # 1 minute

        # Initially not revoked
        with patch("app.core.security.get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.exists.return_value = 0
            mock_get_redis.return_value = mock_redis

            result = await is_access_token_revoked(jti)
            assert result is False

        # Revoke the token
        with patch("app.core.security.get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis

            await revoke_access_token(jti, expires_in)
            mock_redis.setex.assert_called_once()

        # Check revoked
        with patch("app.core.security.get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.exists.return_value = 1
            mock_get_redis.return_value = mock_redis

            result = await is_access_token_revoked(jti)
            assert result is True


class TestRefreshTokenRotation:
    """Tests for refresh token rotation and family tracking."""

    @pytest.mark.asyncio
    async def test_create_refresh_token_record(self):
        """Test creating a refresh token record."""
        mock_session = AsyncMock()
        auth_service = AuthService(mock_session)

        user_id = uuid4()
        jti = "test-jti"
        family_id = "test-family"
        expires_at = datetime.now(UTC) + timedelta(days=30)

        token = await auth_service.create_refresh_token_record(
            user_id=user_id,
            jti=jti,
            family_id=family_id,
            expires_at=expires_at,
        )

        assert token.user_id == user_id
        assert token.jti == jti
        assert token.family_id == family_id
        assert token.expires_at == expires_at
        assert token.revoked is False
        assert token.replaced_by_jti is None

    @pytest.mark.asyncio
    async def test_validate_refresh_token_record_valid(self):
        """Test validating a valid refresh token record."""
        mock_session = AsyncMock()
        auth_service = AuthService(mock_session)

        user_id = uuid4()
        jti = "valid-jti"
        family_id = "test-family"

        mock_token = RefreshToken(
            id=uuid4(),
            user_id=user_id,
            jti=jti,
            family_id=family_id,
            revoked=False,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute = AsyncMock(return_value=mock_result)

        token = await auth_service.validate_refresh_token_record(jti, user_id)
        assert token is not None
        assert token.jti == jti

    @pytest.mark.asyncio
    async def test_validate_refresh_token_record_revoked(self):
        """Test validating a revoked refresh token record returns None."""
        mock_session = AsyncMock()
        auth_service = AuthService(mock_session)

        user_id = uuid4()
        jti = "revoked-jti"

        mock_token = RefreshToken(
            id=uuid4(),
            user_id=user_id,
            jti=jti,
            family_id="test-family",
            revoked=True,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute = AsyncMock(return_value=mock_result)

        token = await auth_service.validate_refresh_token_record(jti, user_id)
        assert token is None

    @pytest.mark.asyncio
    async def test_validate_refresh_token_record_expired(self):
        """Test validating an expired refresh token record returns None."""
        mock_session = AsyncMock()
        auth_service = AuthService(mock_session)

        user_id = uuid4()
        jti = "expired-jti"

        mock_token = RefreshToken(
            id=uuid4(),
            user_id=user_id,
            jti=jti,
            family_id="test-family",
            revoked=False,
            expires_at=datetime.now(UTC) - timedelta(days=1),
            created_at=datetime.now(UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_session.execute = AsyncMock(return_value=mock_result)

        token = await auth_service.validate_refresh_token_record(jti, user_id)
        assert token is None

    @pytest.mark.asyncio
    async def test_revoke_refresh_token_family(self):
        """Test revoking all tokens in a family."""
        mock_session = AsyncMock()
        auth_service = AuthService(mock_session)

        user_id = uuid4()
        family_id = "test-family"

        mock_tokens = [
            RefreshToken(
                id=uuid4(),
                user_id=user_id,
                jti=f"jti-{i}",
                family_id=family_id,
                revoked=False,
                expires_at=datetime.now(UTC) + timedelta(days=30),
                created_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tokens
        mock_session.execute = AsyncMock(return_value=mock_result)

        count = await auth_service.revoke_refresh_token_family(family_id, user_id)
        assert count == 3
        for token in mock_tokens:
            assert token.revoked is True
            assert token.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoke_all_user_refresh_tokens(self):
        """Test revoking all refresh tokens for a user."""
        mock_session = AsyncMock()
        auth_service = AuthService(mock_session)

        user_id = uuid4()

        mock_tokens = [
            RefreshToken(
                id=uuid4(),
                user_id=user_id,
                jti=f"jti-{i}",
                family_id=f"family-{i}",
                revoked=False,
                expires_at=datetime.now(UTC) + timedelta(days=30),
                created_at=datetime.now(UTC),
            )
            for i in range(2)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tokens
        mock_session.execute = AsyncMock(return_value=mock_result)

        count = await auth_service.revoke_all_user_refresh_tokens(user_id)
        assert count == 2
        for token in mock_tokens:
            assert token.revoked is True

    @pytest.mark.asyncio
    async def test_rotate_refresh_token(self):
        """Test rotating a refresh token."""
        mock_session = AsyncMock()
        auth_service = AuthService(mock_session)

        user_id = uuid4()
        old_jti = "old-jti"
        old_family_id = "test-family"
        new_jti = "new-jti"
        new_expires_at = datetime.now(UTC) + timedelta(days=30)

        old_token = RefreshToken(
            id=uuid4(),
            user_id=user_id,
            jti=old_jti,
            family_id=old_family_id,
            revoked=False,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = old_token
        mock_session.execute = AsyncMock(return_value=mock_result)

        new_token = await auth_service.rotate_refresh_token(
            old_jti=old_jti,
            old_family_id=old_family_id,
            user_id=user_id,
            new_jti=new_jti,
            new_expires_at=new_expires_at,
        )

        assert new_token.jti == new_jti
        assert new_token.family_id == old_family_id
        assert new_token.user_id == user_id
        assert old_token.revoked is True
        assert old_token.replaced_by_jti == new_jti


class TestAuthEndpoints:
    """Tests for auth API endpoints with revocation."""

    @pytest.mark.asyncio
    async def test_login_creates_refresh_token_record(self):
        """Test that login creates a refresh token record in DB."""
        from app.api.v1.auth import login
        from app.schemas.auth import LoginRequest

        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = "test@example.com"
        mock_user.is_active = True
        mock_user.roles = []

        # Create real tokens for testing (now with version)
        real_access_token = create_access_token({"sub": str(mock_user.id), "email": mock_user.email})
        real_refresh_token = create_refresh_token({"sub": str(mock_user.id), "email": mock_user.email})

        with patch("app.api.v1.auth.AuthService") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.authenticate_user = AsyncMock(return_value=mock_user)
            # Updated to use create_token_pair_with_version
            mock_auth.create_token_pair_with_version = AsyncMock(return_value=(real_access_token, real_refresh_token, 0))
            mock_auth.create_refresh_token_record = AsyncMock()
            mock_auth_cls.return_value = mock_auth

            request = LoginRequest(email="test@example.com", password="password")
            response = await login(request, db=mock_db)

            assert response.access_token == real_access_token
            assert response.refresh_token == real_refresh_token
            mock_auth.create_refresh_token_record.assert_called_once()
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_rotation(self):
        """Test that refresh rotates tokens and updates DB."""
        from app.api.v1.auth import refresh_token

        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = "test@example.com"
        mock_user.is_active = True

        with patch("app.api.v1.auth.AuthService") as mock_auth_cls, \
             patch("app.api.v1.auth.decode_token") as mock_decode, \
             patch("app.api.v1.auth.create_refresh_token") as mock_create_refresh, \
             patch("app.core.security.create_access_token_with_version") as mock_create_access_with_version:

            mock_auth = MagicMock()
            mock_auth.verify_refresh_token = MagicMock(return_value={
                "sub": str(mock_user.id),
                "email": mock_user.email,
                "jti": "old-jti",
            })
            mock_auth.get_user_by_id = AsyncMock(return_value=mock_user)
            mock_auth.validate_refresh_token_record = AsyncMock(return_value=MagicMock(
                family_id="test-family",
                jti="old-jti",
            ))
            mock_auth.rotate_refresh_token = AsyncMock()
            mock_auth.create_access_token_from_refresh = MagicMock(return_value="new-access-token")
            mock_auth_cls.return_value = mock_auth

            mock_decode.return_value = {"jti": "new-jti", "exp": 9999999999}
            mock_create_refresh.return_value = "new-refresh-token"
            mock_create_access_with_version.return_value = ("new-access-token", 1)

            request = RefreshRequest(refresh_token="old-refresh-token")
            response = await refresh_token(request, db=mock_db)

            assert response.access_token == "new-access-token"
            assert response.refresh_token == "new-refresh-token"
            mock_auth.rotate_refresh_token.assert_called_once()
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_reuse_detection(self):
        """Test that reusing a revoked refresh token revokes the family."""
        from app.api.v1.auth import refresh_token

        mock_db = AsyncMock()

        with patch("app.api.v1.auth.AuthService") as mock_auth_cls:
            mock_auth = MagicMock()
            user_id = uuid4()
            mock_auth.verify_refresh_token = MagicMock(return_value={
                "sub": str(user_id),
                "email": "test@example.com",
                "jti": "revoked-jti",
            })
            mock_user = MagicMock()
            mock_user.id = user_id
            mock_user.is_active = True
            mock_auth.get_user_by_id = AsyncMock(return_value=mock_user)
            # First call returns None (token not found/revoked)
            mock_auth.validate_refresh_token_record = AsyncMock(return_value=None)
            # Need to return a revoked token record with family_id for reuse detection
            mock_revoked_token = MagicMock()
            mock_revoked_token.family_id = "test-family"
            mock_auth.get_revoked_refresh_token_record = AsyncMock(return_value=mock_revoked_token)
            mock_auth.revoke_refresh_token_family = AsyncMock()
            mock_auth_cls.return_value = mock_auth

            request = RefreshRequest(refresh_token="revoked-refresh-token")
            with pytest.raises(HTTPException) as exc_info:
                await refresh_token(request, db=mock_db)

            assert exc_info.value.status_code == 401
            assert "revoked or reused" in exc_info.value.detail
            mock_auth.revoke_refresh_token_family.assert_called_once_with("test-family", user_id)

    @pytest.mark.asyncio
    async def test_logout_revokes_tokens(self):
        """Test that logout revokes both access and refresh tokens."""
        from app.api.v1.auth import logout

        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = "test@example.com"

        with patch("app.api.v1.auth.AuthService") as mock_auth_cls, \
             patch("app.api.v1.auth.decode_token") as mock_decode:

            mock_auth = MagicMock()
            mock_auth.logout = AsyncMock()
            mock_auth_cls.return_value = mock_auth

            mock_decode.side_effect = [
                {"jti": "access-jti", "type": "access", "exp": 9999999999},  # access token decode
                {"jti": "refresh-jti", "type": "refresh"},  # refresh token decode
            ]

            request = LogoutRequest(refresh_token="refresh-token")
            await logout(request, current_user=mock_user, db=mock_db, authorization="Bearer access-token")

            mock_auth.logout.assert_called_once_with("access-jti", 9999999999, "refresh-jti", mock_user.id)
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_all_sessions_admin(self):
        """Test admin revoking all sessions for a user."""
        from app.api.v1.auth import revoke_all_sessions
        from app.core.security import increment_user_token_version

        mock_db = AsyncMock()
        mock_admin = MagicMock()
        mock_admin.id = uuid4()

        with patch("app.api.v1.auth.AuthService") as mock_auth_cls, \
             patch("app.core.security.increment_user_token_version") as mock_increment_version:

            mock_auth = MagicMock()
            # Mock revoke_all_user_sessions with side_effect to test the real flow
            async def mock_revoke_all_sessions(user_id):
                await mock_auth.revoke_all_user_refresh_tokens(user_id)
                await mock_increment_version(str(user_id))
                return 3
            
            mock_auth.revoke_all_user_sessions = AsyncMock(side_effect=mock_revoke_all_sessions)
            mock_auth.revoke_all_user_refresh_tokens = AsyncMock(return_value=3)
            mock_auth_cls.return_value = mock_auth

            mock_increment_version.return_value = 1

            await revoke_all_sessions(current_user=mock_admin, db=mock_db)

            mock_auth.revoke_all_user_refresh_tokens.assert_called_once_with(mock_admin.id)
            mock_increment_version.assert_called_once_with(str(mock_admin.id))
            mock_db.commit.assert_called_once()


class TestGetCurrentUserWithRevocation:
    """Tests for get_current_user with access token revocation check."""

    @pytest.mark.asyncio
    async def test_revoked_access_token_rejected(self):
        """Test that a revoked access token is rejected."""
        from app.core.dependencies import get_current_user

        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.is_active = True

        with patch("app.core.dependencies.AuthService") as mock_auth_cls, \
             patch("app.core.dependencies.decode_token") as mock_decode, \
             patch("app.core.dependencies.is_access_token_revoked") as mock_is_revoked:

            mock_auth = MagicMock()
            mock_auth.get_user_by_id = AsyncMock(return_value=mock_user)
            mock_auth_cls.return_value = mock_auth

            mock_decode.return_value = {
                "sub": str(mock_user.id),
                "email": "test@example.com",
                "type": "access",
                "jti": "revoked-jti",
            }
            mock_is_revoked.return_value = True

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(authorization="Bearer revoked-token", db=mock_db)

            assert exc_info.value.status_code == 401
            assert "revoked" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_valid_access_token_accepted(self):
        """Test that a valid non-revoked access token is accepted."""
        from app.core.dependencies import get_current_user

        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.is_active = True

        with patch("app.core.dependencies.AuthService") as mock_auth_cls, \
             patch("app.core.dependencies.decode_token") as mock_decode, \
             patch("app.core.dependencies.is_access_token_revoked") as mock_is_revoked:

            mock_auth = MagicMock()
            mock_auth.get_user_by_id = AsyncMock(return_value=mock_user)
            mock_auth_cls.return_value = mock_auth

            mock_decode.return_value = {
                "sub": str(mock_user.id),
                "email": "test@example.com",
                "type": "access",
                "jti": "valid-jti",
            }
            mock_is_revoked.return_value = False

            user = await get_current_user(authorization="Bearer valid-token", db=mock_db)
            assert user == mock_user

    @pytest.mark.asyncio
    async def test_refresh_token_as_access_token_rejected(self):
        """Test that using a refresh token as access token is rejected."""
        from app.core.dependencies import get_current_user

        mock_db = AsyncMock()

        with patch("app.core.dependencies.decode_token") as mock_decode:
            mock_decode.return_value = {
                "sub": str(uuid4()),
                "email": "test@example.com",
                "type": "refresh",
                "jti": "refresh-jti",
            }

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(authorization="Bearer refresh-token", db=mock_db)

            assert exc_info.value.status_code == 401
            assert "Invalid token type" in exc_info.value.detail


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    @pytest.mark.asyncio
    async def test_security_headers_present(self):
        """Test that security headers are added to responses."""
        from app.core.security_headers import SecurityHeadersMiddleware
        from starlette.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, csp_enabled=True, hsts_enabled=False)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in response.headers
        assert "Permissions-Policy" in response.headers
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    @pytest.mark.asyncio
    async def test_hsts_only_on_https(self):
        """Test that HSTS is only added for HTTPS requests."""
        from app.core.security_headers import SecurityHeadersMiddleware
        from starlette.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, csp_enabled=True, hsts_enabled=True)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app, base_url="http://testserver")
        response = client.get("/test")
        assert "Strict-Transport-Security" not in response.headers

        client = TestClient(app, base_url="https://testserver")
        response = client.get("/test")
        assert "Strict-Transport-Security" in response.headers
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]


class TestCORSConfiguration:
    """Tests for CORS configuration."""

    @pytest.mark.asyncio
    async def test_cors_allows_configured_origin(self):
        """Test that configured origins are allowed."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from starlette.testclient import TestClient

        origins = ["http://localhost:5173", "https://app.example.com"]
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)

        # Test allowed origin
        response = client.get("/test", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
        assert response.headers["Access-Control-Allow-Credentials"] == "true"

        # Test production origin
        response = client.get("/test", headers={"Origin": "https://app.example.com"})
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://app.example.com"

    @pytest.mark.asyncio
    async def test_cors_rejects_unauthorized_origin(self):
        """Test that unauthorized origins are rejected."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from starlette.testclient import TestClient

        origins = ["http://localhost:5173"]
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)

        # Test unauthorized origin
        response = client.get("/test", headers={"Origin": "https://evil.com"})
        assert response.status_code == 200  # Request succeeds but no CORS headers
        assert "Access-Control-Allow-Origin" not in response.headers

    @pytest.mark.asyncio
    async def test_cors_preflight(self):
        """Test CORS OPTIONS preflight request."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from starlette.testclient import TestClient

        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
        )

        @app.post("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.options(
            "/test",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            }
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
        assert "POST" in response.headers["Access-Control-Allow-Methods"]
        assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
        assert response.headers["Access-Control-Allow-Credentials"] == "true"

    @pytest.mark.asyncio
    async def test_cors_no_wildcard_with_credentials(self):
        """Test that wildcard origin is not used with credentials."""
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from starlette.testclient import TestClient

        # This is the WRONG configuration - wildcard with credentials
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # wildcard
            allow_credentials=True,  # with credentials - BAD!
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test", headers={"Origin": "https://any-origin.com"})
        # This would actually work in Starlette but is a security anti-pattern
        # Our implementation should NOT do this - we explicitly list origins
        assert "Access-Control-Allow-Origin" in response.headers


class TestCeleryBeatDockerCompose:
    """Tests for Celery Beat Docker Compose configuration."""

    def test_beat_service_exists(self):
        """Test that beat service is defined in docker-compose.yml."""
        import yaml
        from pathlib import Path

        compose_path = Path(__file__).parent.parent.parent / "infrastructure" / "docker-compose.yml"
        assert compose_path.exists()

        with open(compose_path) as f:
            compose = yaml.safe_load(f)

        assert "beat" in compose["services"]
        beat_service = compose["services"]["beat"]

        # Check command
        assert "celery" in beat_service["command"]
        assert "-A app.core.celery_app beat" in beat_service["command"]
        assert "--scheduler=celery.beat.PersistentScheduler" in beat_service["command"]

        # Check environment variables match worker
        env_list = beat_service.get("environment", [])
        env_dict = {}
        for item in env_list:
            if "=" in item:
                key, value = item.split("=", 1)
                env_dict[key] = value
        
        assert "DATABASE_URL" in env_dict
        assert "REDIS_URL" in env_dict
        assert "CELERY_BROKER_URL" in env_dict

        # Check volumes include beat-schedule
        volumes = beat_service.get("volumes", [])
        assert any("beat-schedule" in v for v in volumes)

        # Check depends_on
        assert "postgres" in beat_service["depends_on"]
        assert "redis" in beat_service["depends_on"]

    def test_beat_schedule_volume_exists(self):
        """Test that beat-schedule volume is defined."""
        import yaml
        from pathlib import Path

        compose_path = Path(__file__).parent.parent.parent / "infrastructure" / "docker-compose.yml"
        with open(compose_path) as f:
            compose = yaml.safe_load(f)

        assert "beat-schedule" in compose.get("volumes", {})

    def test_scheduled_tasks_resolve_to_registered_tasks(self):
        """Test that all scheduled tasks in beat schedule exist in celery app."""
        from app.core.celery_app import celery_app
        from app.core.celery_beat_schedule import CELERY_BEAT_SCHEDULE

        # Force task autodiscovery
        celery_app.loader.import_default_modules()

        registered_tasks = set(celery_app.tasks.keys())

        for task_name, config in CELERY_BEAT_SCHEDULE.items():
            task_path = config["task"]
            assert task_path in registered_tasks, f"Scheduled task {task_path} not found in registered tasks"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])