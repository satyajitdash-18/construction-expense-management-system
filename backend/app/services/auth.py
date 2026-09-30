from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_redis
from app.core.security import (
    create_access_token_from_refresh,
    create_refresh_token,
    create_token_pair_with_version,
    decode_token,
    get_password_hash,
    increment_user_token_version,
    verify_password,
    revoke_access_token,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.user import UserRepository


class AuthService:
    def __init__(self, session: AsyncSession):
        self.user_repo = UserRepository(session)

    async def authenticate_user(self, email: str, password: str) -> User | None:
        user = await self.user_repo.get_by_email(email)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def create_user(
        self, email: str, password: str, full_name: str | None = None, role_names: list[str] | None = None
    ) -> User:
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise ValueError("User with this email already exists")

        hashed_password = get_password_hash(password)
        user = await self.user_repo.create(email=email, hashed_password=hashed_password, full_name=full_name)

        if role_names:
            roles = await self.user_repo.get_roles_by_names(role_names)
            if len(roles) != len(role_names):
                found = {r.name for r in roles}
                missing = set(role_names) - found
                raise ValueError(f"Roles not found: {missing}")
            user = await self.user_repo.assign_roles(user, roles)

        return user

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        return await self.user_repo.get_by_id(user_id)

    async def create_refresh_token_record(
        self,
        user_id: UUID,
        jti: str,
        family_id: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Create a new refresh token record in the database."""
        refresh_token = RefreshToken(
            user_id=user_id,
            jti=jti,
            family_id=family_id,
            expires_at=expires_at,
            revoked=False,
        )
        self.user_repo.session.add(refresh_token)
        await self.user_repo.session.flush()
        return refresh_token

    async def verify_refresh_token(self, refresh_token: str) -> dict:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type, refresh token required")
        return payload

    async def validate_refresh_token_record(self, jti: str, user_id: UUID) -> RefreshToken | None:
        """Validate that a refresh token exists, is not revoked, and belongs to the user."""
        result = await self.user_repo.session.execute(
            select(RefreshToken).where(
                RefreshToken.jti == jti,
                RefreshToken.user_id == user_id,
            )
        )
        token_record = result.scalar_one_or_none()
        if not token_record:
            return None
        if token_record.revoked:
            return None
        if token_record.expires_at < datetime.now(UTC):
            return None
        return token_record

    async def get_revoked_refresh_token_record(self, jti: str, user_id: UUID) -> RefreshToken | None:
        """Get a revoked refresh token record (for reuse detection)."""
        result = await self.user_repo.session.execute(
            select(RefreshToken).where(
                RefreshToken.jti == jti,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_token_family(self, family_id: str, user_id: UUID) -> int:
        """Revoke all tokens in a family (used when reuse is detected)."""
        result = await self.user_repo.session.execute(
            select(RefreshToken).where(
                RefreshToken.family_id == family_id,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked == False,  # noqa: E712
            )
        )
        tokens = result.scalars().all()
        count = 0
        for token in tokens:
            token.revoked = True
            token.revoked_at = datetime.now(UTC)
            count += 1
        await self.user_repo.session.flush()
        return count

    async def revoke_refresh_token(self, jti: str, user_id: UUID) -> bool:
        """Revoke a specific refresh token."""
        result = await self.user_repo.session.execute(
            select(RefreshToken).where(
                RefreshToken.jti == jti,
                RefreshToken.user_id == user_id,
            )
        )
        token = result.scalar_one_or_none()
        if not token:
            return False
        token.revoked = True
        token.revoked_at = datetime.now(UTC)
        await self.user_repo.session.flush()
        return True

    async def revoke_all_user_refresh_tokens(self, user_id: UUID) -> int:
        """Revoke all refresh tokens for a user."""
        result = await self.user_repo.session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked == False,  # noqa: E712
            )
        )
        tokens = result.scalars().all()
        count = 0
        for token in tokens:
            token.revoked = True
            token.revoked_at = datetime.now(UTC)
            count += 1
        await self.user_repo.session.flush()
        return count

    def create_access_token_from_refresh(self, payload: dict) -> str:
        return create_access_token_from_refresh(payload)

    async def rotate_refresh_token(
        self,
        old_jti: str,
        old_family_id: str,
        user_id: UUID,
        new_jti: str,
        new_expires_at: datetime,
    ) -> RefreshToken:
        """Rotate a refresh token: mark old as revoked and create new one in same family."""
        # Mark old token as revoked and replaced
        result = await self.user_repo.session.execute(
            select(RefreshToken).where(
                RefreshToken.jti == old_jti,
                RefreshToken.user_id == user_id,
            )
        )
        old_token = result.scalar_one_or_none()
        if old_token:
            old_token.revoked = True
            old_token.revoked_at = datetime.now(UTC)
            old_token.replaced_by_jti = new_jti

        # Create new token in same family
        new_token = RefreshToken(
            user_id=user_id,
            jti=new_jti,
            family_id=old_family_id,
            expires_at=new_expires_at,
            revoked=False,
        )
        self.user_repo.session.add(new_token)
        await self.user_repo.session.flush()
        return new_token

    async def logout(self, access_token_jti: str | None, access_token_exp: int | None, refresh_token_jti: str | None, user_id: UUID) -> None:
        """Logout: revoke access token (via Redis) and refresh token (via DB)."""
        # Revoke access token - calculate remaining TTL from JWT exp claim
        if access_token_jti and access_token_exp:
            from app.core.security import _calculate_blacklist_ttl
            ttl = _calculate_blacklist_ttl(access_token_exp)
            await revoke_access_token(access_token_jti, ttl)

        # Revoke refresh token
        if refresh_token_jti:
            await self.revoke_refresh_token(refresh_token_jti, user_id)

    async def revoke_all_user_sessions(self, user_id: UUID) -> int:
        """Revoke all sessions for a user (admin action).
        
        Increments user token version to immediately invalidate all access tokens,
        and revokes all refresh tokens in DB.
        """
        # Revoke all refresh tokens
        refresh_count = await self.revoke_all_user_refresh_tokens(user_id)
        # Increment user token version to immediately invalidate all access tokens
        await increment_user_token_version(str(user_id))
        return refresh_count