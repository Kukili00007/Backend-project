from __future__ import annotations

from collections.abc import AsyncIterator

from redis.asyncio import Redis, from_url

from app.config import get_settings

_redis_client: Redis | None = None


async def create_redis_pool() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def close_redis_pool() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def get_redis() -> AsyncIterator[Redis]:
    redis = await create_redis_pool()
    yield redis

