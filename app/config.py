from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LeanStock Inventory API"
    app_env: Literal["development", "test", "production"] = "development"
    secret_key: str = Field(..., min_length=32)
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
    from_email: str = "noreply@leanstock.kz"
    sendgrid_api_key: str | None = None
    email_provider: Literal["gmail_oauth2"] = "gmail_oauth2"
    email_enabled: bool = True
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_refresh_token: str | None = None
    google_oauth_token_uri: str = "https://oauth2.googleapis.com/token"
    gmail_sender_email: str | None = None
    frontend_base_url: str | None = None
    api_base_url: str = "http://localhost:8000"
    email_verification_token_expire_hours: int = Field(default=24, ge=1)
    password_reset_token_expire_minutes: int = Field(default=30, ge=5)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env == "production" and "*" in self.cors_origins:
            raise ValueError("Wildcard CORS origins are forbidden in production.")
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
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
