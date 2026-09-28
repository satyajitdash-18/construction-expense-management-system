from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_project_manager
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest, db: AsyncSession = Depends(get_db), authorization: str | None = Header(default=None)
) -> TokenResponse:
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(request.email, request.password)

    if not user:
        logger.warning("login_failed", email=request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, refresh_token = auth_service.create_token_pair(user)

    logger.info("login_success", user_id=str(user.id), email=user.email)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    auth_service = AuthService(db)

    try:
        payload = auth_service.verify_refresh_token(request.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await auth_service.get_user_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth_service.create_access_token_from_refresh(payload)
    refresh_token = auth_service.create_token_pair(user)[1]

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "roles": [role.name for role in current_user.roles],
    }


@router.get("/admin-only")
async def admin_only_endpoint(current_user: User = Depends(require_admin)) -> dict:
    return {"message": "Admin access granted", "user": current_user.email}


@router.get("/pm-or-admin")
async def pm_or_admin_endpoint(current_user: User = Depends(require_project_manager)) -> dict:
    return {"message": "PM or Admin access granted", "user": current_user.email}
