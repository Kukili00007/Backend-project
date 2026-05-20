from __future__ import annotations

from app.config import Settings


def test_effective_cors_origins_adds_deployrocks_frontend_origin(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-with-at-least-32-chars")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db/leanstock")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("CORS_ORIGINS", "https://kukili00007-backend-project-frontend.kazi.rocks")
    monkeypatch.setenv("API_BASE_URL", "https://kukili00007-backend-project-api.kazi.rocks/health")
    monkeypatch.setenv("FRONTEND_BASE_URL", "")

    settings = Settings()

    assert settings.effective_cors_origins == [
        "https://kukili00007-backend-project-frontend.kazi.rocks",
    ]
