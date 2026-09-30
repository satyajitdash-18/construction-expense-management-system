"""Security headers middleware for HTTP response hardening."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all HTTP responses."""

    def __init__(self, app, csp_enabled: bool = True, hsts_enabled: bool = False):
        super().__init__(app)
        self.csp_enabled = csp_enabled
        self.hsts_enabled = hsts_enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        if self.csp_enabled:
            csp = self._build_csp(request)
            response.headers["Content-Security-Policy"] = csp

        # Strict Transport Security (only for HTTPS)
        if self.hsts_enabled and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Permissions policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # X-XSS-Protection (legacy but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        return response

    def _build_csp(self, request: Request) -> str:
        """Build Content-Security-Policy header value."""
        # In development, allow Swagger UI and less restrictive policies
        if settings.APP_ENV in ("development", "dev", "test", "testing"):
            return (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "connect-src 'self' https:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )

        # Production: stricter CSP
        return (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )


def add_security_headers_middleware(app, csp_enabled: bool = True, hsts_enabled: bool = False) -> None:
    """Add security headers middleware to FastAPI app."""
    app.add_middleware(SecurityHeadersMiddleware, csp_enabled=csp_enabled, hsts_enabled=hsts_enabled)