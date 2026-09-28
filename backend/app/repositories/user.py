from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.role import Role
from app.models.user import User

if TYPE_CHECKING:
    from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create(self, email: str, hashed_password: str, full_name: str | None = None) -> User:
        user = User(email=email, hashed_password=hashed_password, full_name=full_name)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user, attribute_names=["roles"])
        return user

    async def update(self, user: User) -> User:
        await self.session.flush()
        await self.session.refresh(user, attribute_names=["roles"])
        return user

    async def get_roles_by_names(self, role_names: list[str]) -> list[Role]:
        result = await self.session.execute(select(Role).where(Role.name.in_(role_names)))
        return list(result.scalars().all())

    async def assign_roles(self, user: User, roles: list[Role]) -> User:
        user.roles = roles
        await self.session.flush()
        await self.session.refresh(user, attribute_names=["roles"])
        return user
