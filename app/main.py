from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.config import get_settings
from app.core.redis_client import close_redis_pool, create_redis_pool
from app.errors import register_exception_handlers
from app.routers import admin, auth, inventory, products, transfers, warehouses

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_redis_pool()
    yield
    await close_redis_pool()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "LeanStock backend with JWT auth/RBAC, email verification, password reset, "
        "multi-tenant catalog, atomic inventory transfers, Redis reservations, "
        "Gmail OAuth2 email delivery, and scheduled dead-stock decay."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

register_exception_handlers(app)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    app.openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/health", tags=["Health"], summary="Health check", include_in_schema=True)
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router, prefix="/v1")
app.include_router(warehouses.router, prefix="/v1")
app.include_router(products.router, prefix="/v1")
app.include_router(inventory.router, prefix="/v1")
app.include_router(transfers.router, prefix="/v1")
app.include_router(admin.router, prefix="/v1")
