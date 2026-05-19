from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings

settings = get_settings()

engine_options = {
    "future": True,
    "echo": False,
    "pool_pre_ping": True,
}
if settings.app_env == "test" or settings.database_null_pool:
    engine_options["poolclass"] = NullPool
else:
    engine_options["pool_size"] = 10
    engine_options["max_overflow"] = 20

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    **engine_options,
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


async def close_database_pool() -> None:
    await engine.dispose()
