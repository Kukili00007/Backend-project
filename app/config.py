from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LeanStock Inventory API"
    app_env: Literal["development", "test", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"),
    )
    secret_key: str = Field(
        ...,
        min_length=32,
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET_KEY"),
    )
    jwt_refresh_secret_key: str | None = Field(default=None, validation_alias="JWT_REFRESH_SECRET_KEY")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1)
    refresh_token_expire_days: int = Field(default=7, ge=1)
    database_url: str
    redis_url: str
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    reservation_ttl_seconds: int = Field(default=900, ge=60)
    auth_rate_limit_per_minute: int = Field(default=5, ge=1)
    decay_start_days: int = Field(default=30, ge=1)
    decay_interval_hours: int = Field(default=72, ge=1)
    decay_discount_pct: Decimal = Field(default=Decimal("10"), gt=0, le=100)
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    from_email: str = Field(
        default="noreply@leanstock.kz",
        validation_alias=AliasChoices("FROM_EMAIL", "EMAIL_FROM_ADDRESS"),
    )
    sendgrid_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SENDGRID_API_KEY", "EMAIL_API_KEY"),
    )
    email_provider: Literal["gmail_oauth2"] = "gmail_oauth2"
    email_enabled: bool = True
    google_oauth_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GMAIL_OAUTH_CLIENT_ID",
            "LEANSTOCK_GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_ID",
        ),
    )
    google_oauth_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GMAIL_OAUTH_CLIENT_CREDENTIAL",
            "LEANSTOCK_GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_CLIENT_SECRET",
        ),
    )
    google_oauth_refresh_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "GMAIL_OAUTH_REFRESH_CREDENTIAL",
            "LEANSTOCK_GOOGLE_OAUTH_REFRESH_TOKEN",
            "GOOGLE_OAUTH_REFRESH_TOKEN",
        ),
    )
    google_oauth_token_uri: str = Field(
        default="https://oauth2.googleapis.com/token",
        validation_alias=AliasChoices("LEANSTOCK_GOOGLE_OAUTH_TOKEN_URI", "GOOGLE_OAUTH_TOKEN_URI"),
    )
    gmail_sender_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LEANSTOCK_GMAIL_SENDER_EMAIL", "GMAIL_SENDER_EMAIL"),
    )
    frontend_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LEANSTOCK_FRONTEND_BASE_URL", "FRONTEND_BASE_URL"),
    )
    api_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices("LEANSTOCK_API_BASE_URL", "API_BASE_URL"),
    )
    backend_port: int = Field(default=8000, validation_alias="BACKEND_PORT")
    frontend_port: int = Field(default=3000, validation_alias="FRONTEND_PORT")
    email_verification_token_expire_hours: int = Field(default=24, ge=1)
    password_reset_token_expire_minutes: int = Field(default=30, ge=5)
    database_null_pool: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator(
        "access_token_expire_minutes",
        "refresh_token_expire_days",
        "email_verification_token_expire_hours",
        "password_reset_token_expire_minutes",
        mode="before",
    )
    @classmethod
    def normalize_integer_setting(cls, value: object, info) -> int:
        defaults = {
            "access_token_expire_minutes": 30,
            "refresh_token_expire_days": 7,
            "email_verification_token_expire_hours": 24,
            "password_reset_token_expire_minutes": 30,
        }
        if value in (None, ""):
            return defaults[info.field_name]
        try:
            return int(value)
        except (TypeError, ValueError):
            return defaults[info.field_name]

    @field_validator("google_oauth_token_uri", mode="before")
    @classmethod
    def normalize_google_oauth_token_uri(cls, value: str | None) -> str:
        if not value or not value.startswith(("http://", "https://")):
            return "https://oauth2.googleapis.com/token"
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env != "production":
            return self

        if self.secret_key.startswith("change-me"):
            raise ValueError("SECRET_KEY must be replaced before production boot.")
        if not self.jwt_refresh_secret_key or self.jwt_refresh_secret_key.startswith("change-me"):
            raise ValueError("JWT_REFRESH_SECRET_KEY must be replaced before production boot.")
        if not self.cors_origins:
            raise ValueError("CORS_ORIGINS must be explicitly configured in production.")
        if "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are forbidden in production.")
        if self.email_enabled:
            email_values = {
                "GOOGLE_OAUTH_CLIENT_ID": self.google_oauth_client_id,
                "GOOGLE_OAUTH_CLIENT_SECRET": self.google_oauth_client_secret,
                "GOOGLE_OAUTH_REFRESH_TOKEN": self.google_oauth_refresh_token,
                "GMAIL_SENDER_EMAIL": self.gmail_sender_email,
            }
            missing_or_placeholder = [
                name
                for name, value in email_values.items()
                if not value or value.startswith("replace-with") or value.startswith("your-")
            ]
            if missing_or_placeholder:
                missing = ", ".join(missing_or_placeholder)
                raise ValueError(f"Production email delivery requires real values for: {missing}.")
        return self

    @property
    def access_token_expire_seconds(self) -> int:
        return self.access_token_expire_minutes * 60

    @property
    def refresh_token_expire_seconds(self) -> int:
        return self.refresh_token_expire_days * 24 * 60 * 60

    @property
    def effective_sender_email(self) -> str:
        return self.gmail_sender_email or self.from_email

    @property
    def effective_refresh_secret_key(self) -> str:
        return self.jwt_refresh_secret_key or self.secret_key

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
