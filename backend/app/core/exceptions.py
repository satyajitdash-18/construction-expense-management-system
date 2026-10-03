from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.requests import Request as StarletteRequest

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 500, details: dict | None = None) -> None:
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(AppException):
    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            message=f"{resource} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "identifier": identifier},
        )


class ConflictError(AppException):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Invalid credentials") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "Not permitted") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class RequestValidationError(AppException):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


async def app_exception_handler(request: StarletteRequest, exc: AppException) -> JSONResponse:
    logger.error(
        "application_error",
        path=request.url.path,
        method=request.method,
        error=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "details": exc.details},
    )


async def validation_exception_handler(request: StarletteRequest, exc: PydanticValidationError) -> JSONResponse:
    sanitized_errors = []
    for err in exc.errors():
        sanitized_errors.append({
            "loc": [str(x) for x in err.get("loc", [])],
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", "")),
        })
    logger.warning(
        "validation_error",
        path=request.url.path,
        method=request.method,
        errors=sanitized_errors,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Validation failed", "details": sanitized_errors},
    )


async def generic_exception_handler(request: StarletteRequest, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_error",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)
