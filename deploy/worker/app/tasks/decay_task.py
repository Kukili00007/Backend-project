from __future__ import annotations

import asyncio

from app.config import get_settings
from app.database import async_session_factory
from app.services.decay_service import run_decay_cycle
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.decay_task.run_dead_stock_decay")
def run_dead_stock_decay() -> dict[str, int]:
    async def _run() -> dict[str, int]:
        async with async_session_factory() as session:
            result = await run_decay_cycle(session=session, settings=get_settings())
            return {
                "marked_liquidating": result.marked_liquidating,
                "discounted": result.discounted,
            }

    return asyncio.run(_run())

