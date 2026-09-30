from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role_names: list[str] | None = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    is_active: bool
    roles: list[str]

    model_config = ConfigDict(from_attributes=True)

