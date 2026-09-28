from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
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

    def create_token_pair(self, user: User) -> tuple[str, str]:
        return create_access_token({"sub": str(user.id), "email": user.email}), create_refresh_token(
            {"sub": str(user.id), "email": user.email}
        )

    def verify_refresh_token(self, refresh_token: str) -> dict:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type, refresh token required")
        return payload

    def create_access_token_from_refresh(self, payload: dict) -> str:
        return create_access_token({"sub": payload["sub"], "email": payload["email"]})
