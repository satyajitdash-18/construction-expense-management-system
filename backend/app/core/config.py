from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me-in-production"
    API_V1_PREFIX: str = "/api/v1"

    POSTGRES_SERVER: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "construction_expense"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/construction_expense"

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://redis:6379/0"

    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "evidence"
    MINIO_SECURE: bool = False

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    TESSERACT_CMD: str = "tesseract"
    TESSERACT_LANG: str = "eng+hin"
    TESSERACT_CONFIG: str = "--psm 6 --oem 3"

    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 2000
    LLM_TIMEOUT_SECONDS: int = 60

    EXPORT_DIR: str = "/tmp/audit_exports"

    SENTRY_DSN: str = ""

    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    FCM_SERVER_KEY: str = ""

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: int = 120
    RATE_LIMIT_AUTH: int = 5
    RATE_LIMIT_WEBHOOK: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        env = (self.APP_ENV or "development").strip().lower()
        if env not in ("development", "dev", "test", "testing"):
            insecure_defaults = {"change-me-in-production", "secret", "changeme", "admin"}
            if self.JWT_SECRET_KEY in insecure_defaults or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    f"JWT_SECRET_KEY must be securely configured with at least 32 characters in {self.APP_ENV} environment."
                )
            if self.APP_SECRET_KEY in insecure_defaults or len(self.APP_SECRET_KEY) < 32:
                raise ValueError(
                    f"APP_SECRET_KEY must be securely configured with at least 32 characters in {self.APP_ENV} environment."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
