import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.database import get_redis

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)  # type: ignore[no-any-return]


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)  # type: ignore[no-any-return]


def _generate_jti() -> str:
    return secrets.token_urlsafe(32)


def _get_access_token_redis_key(jti: str) -> str:
    return f"access_token_blacklist:{jti}"


def _get_user_token_version_key(user_id: str) -> str:
    return f"user_token_version:{user_id}"


async def get_user_token_version(user_id: str) -> int:
    """Get the current token version for a user."""
    redis_client = await get_redis()
    version = await redis_client.get(_get_user_token_version_key(user_id))
    return int(version) if version else 0


async def increment_user_token_version(user_id: str) -> int:
    """Increment the user's token version (revokes all existing access tokens)."""
    redis_client = await get_redis()
    new_version = await redis_client.incr(_get_user_token_version_key(user_id))
    return new_version


async def is_access_token_revoked(jti: str, user_id: str | None = None, token_version: int | None = None) -> bool:
    """Check if an access token is revoked.
    
    Checks both:
    1. Individual JTI blacklist (for logout)
    2. User token version (for revoke-all)
    """
    redis_client = await get_redis()
    
    # Check individual blacklist
    if await redis_client.exists(_get_access_token_redis_key(jti)) > 0:
        return True
    
    # Check user token version if provided
    if user_id is not None and token_version is not None:
        current_version = await get_user_token_version(user_id)
        if token_version < current_version:
            return True
    
    return False


async def revoke_access_token(jti: str, expires_in: int) -> None:
    """Add an access token JTI to the revocation blacklist with TTL.
    
    Args:
        jti: The JWT ID to blacklist
        expires_in: TTL in seconds. Must not exceed the remaining token lifetime.
    """
    redis_client = await get_redis()
    await redis_client.setex(_get_access_token_redis_key(jti), expires_in, "1")


def _calculate_blacklist_ttl(exp_timestamp: int) -> int:
    """Calculate remaining TTL for blacklist from JWT exp claim.
    
    Args:
        exp_timestamp: Unix timestamp from JWT exp claim
        
    Returns:
        TTL in seconds, minimum 1 second, maximum remaining lifetime
    """
    now = datetime.now(UTC).timestamp()
    remaining = int(exp_timestamp - now)
    return max(1, remaining)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access", "jti": _generate_jti()})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)  # type: ignore[no-any-return]


async def create_access_token_with_version(
    data: dict, user_id: str, expires_delta: timedelta | None = None
) -> tuple[str, int]:
    """Create access token with user token version for revoke-all support.
    
    Returns:
        Tuple of (token_string, token_version)
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Get current user token version
    token_version = await get_user_token_version(user_id)
    
    jti = _generate_jti()
    to_encode.update({"exp": expire, "type": "access", "jti": jti, "tv": token_version})
    token = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)  # type: ignore[no-any-return]
    return token, token_version


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": _generate_jti()})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)  # type: ignore[no-any-return]


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])  # type: ignore[no-any-return]


def create_token_pair(user_id: str, email: str) -> tuple[str, str]:
    access_token = create_access_token({"sub": user_id, "email": email})
    refresh_token = create_refresh_token({"sub": user_id, "email": email})
    return access_token, refresh_token


def create_access_token_from_refresh(payload: dict) -> str:
    """Create a new access token from a refresh token payload."""
    return create_access_token({"sub": payload["sub"], "email": payload["email"]})


async def create_token_pair_with_version(user_id: str, email: str) -> tuple[str, str, int]:
    """Create access and refresh token pair with user token version.
    
    Returns:
        Tuple of (access_token, refresh_token, access_token_version)
    """
    access_token, token_version = await create_access_token_with_version(
        {"sub": user_id, "email": email}, user_id
    )
    refresh_token = create_refresh_token({"sub": user_id, "email": email})
    return access_token, refresh_token, token_version


def generate_webhook_signature(payload: dict, secret: str) -> str:
    """Generate HMAC signature for webhook payload."""
    import json
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return signature


def validate_safe_webhook_url(url: str, allow_local: bool = False) -> str:
    """Validate that a webhook URL does not target loopback, private, or metadata IPs (SSRF prevention)."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Prohibited URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a valid hostname.")

    blocked_hostnames = {
        "localhost",
        "metadata.google.internal",
        "instance-data",
        "redis",
        "postgres",
        "minio",
    }
    if hostname.lower() in blocked_hostnames and not allow_local:
        raise ValueError(f"Webhook URL target '{hostname}' is not permitted.")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"Unable to resolve webhook hostname '{hostname}': {e}") from e

    for addr in addr_info:
        ip_str = addr[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if not allow_local and (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(f"Webhook URL cannot target internal, private, or metadata IP address: {ip_str}")

    return url