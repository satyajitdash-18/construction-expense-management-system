import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin, require_project_manager
from app.core.logging import get_logger
from app.core.security import create_refresh_token, decode_token
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse
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

    # Create token pair with version for revoke-all support
    access_token, refresh_token, token_version = await auth_service.create_token_pair_with_version(user)

    # Store refresh token record
    access_payload = decode_token(access_token)
    refresh_payload = decode_token(refresh_token)
    access_jti = access_payload.get("jti")
    refresh_jti = refresh_payload.get("jti")
    family_id = secrets.token_urlsafe(16)
    expires_at = datetime.fromtimestamp(refresh_payload["exp"], UTC)

    await auth_service.create_refresh_token_record(
        user_id=user.id,
        jti=refresh_jti,
        family_id=family_id,
        expires_at=expires_at,
    )
    await db.commit()

    logger.info("login_success", user_id=str(user.id), email=user.email, token_version=token_version)

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
    refresh_jti = payload.get("jti")
    family_id = payload.get("family_id")

    if not user_id or not refresh_jti:
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

    # Validate refresh token record exists and is not revoked
    token_record = await auth_service.validate_refresh_token_record(refresh_jti, UUID(user_id))
    if not token_record:
        # Check if this is a reuse attack - token was revoked but someone is trying to use it
        logger.warning("refresh_token_reuse_detected", user_id=user_id, jti=refresh_jti)
        revoked_token = await auth_service.get_revoked_refresh_token_record(refresh_jti, UUID(user_id))
        if revoked_token:
            await auth_service.revoke_refresh_token_family(revoked_token.family_id, UUID(user_id))
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked or reused",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Rotate: create new access and refresh tokens
    # Create new access token with current user token version
    from app.core.security import create_access_token_with_version
    new_access_token, new_token_version = await create_access_token_with_version(
        {"sub": payload["sub"], "email": payload["email"]}, user_id
    )

    # Create new refresh token with same family_id
    new_refresh_payload = {"sub": payload["sub"], "email": payload["email"], "family_id": token_record.family_id}
    new_refresh_token = create_refresh_token(new_refresh_payload)
    new_refresh_payload_decoded = decode_token(new_refresh_token)
    new_refresh_jti = new_refresh_payload_decoded.get("jti")
    new_expires_at = datetime.fromtimestamp(new_refresh_payload_decoded["exp"], UTC)

    # Rotate in database
    await auth_service.rotate_refresh_token(
        old_jti=refresh_jti,
        old_family_id=token_record.family_id,
        user_id=UUID(user_id),
        new_jti=new_refresh_jti,
        new_expires_at=new_expires_at,
    )
    await db.commit()

    logger.info("refresh_success", user_id=user_id, new_token_version=new_token_version)

    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> None:
    """Logout current user: revoke access token and refresh token."""
    auth_service = AuthService(db)

    access_jti = None
    access_exp = None
    if authorization and authorization.startswith("Bearer "):
        access_token = authorization.split(" ")[1]
        try:
            payload = decode_token(access_token)
            access_jti = payload.get("jti")
            access_exp = payload.get("exp")
        except Exception:
            pass

    refresh_jti = None
    if request.refresh_token:
        try:
            payload = decode_token(request.refresh_token)
            refresh_jti = payload.get("jti")
        except Exception:
            pass

    await auth_service.logout(access_jti, access_exp, refresh_jti, current_user.id)
    await db.commit()

    logger.info("logout_success", user_id=str(current_user.id))


@router.post("/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_sessions(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Admin endpoint: revoke all sessions for a user.
    
    Increments user token version to immediately invalidate all access tokens,
    and revokes all refresh tokens in DB.
    """
    auth_service = AuthService(db)

    user_id = current_user.id
    count = await auth_service.revoke_all_user_sessions(user_id)
    await db.commit()

    logger.info("revoke_all_sessions", user_id=str(user_id), revoked_refresh_count=count)


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