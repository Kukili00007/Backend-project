from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import role_value
from app.errors import AppException
from app.models.product import Product, ProductVariant
from app.models.user import UserRole
from app.models.warehouse import Warehouse
from app.pagination import decode_cursor, encode_cursor
from app.schemas import (
    ProductCreateRequest,
    ProductPageResponse,
    ProductResponse,
    ProductUpdateRequest,
    ProductVariantResponse,
    ProductVariantUpdateRequest,
    WarehouseCreateRequest,
    WarehousePageResponse,
    WarehouseResponse,
    WarehouseUpdateRequest,
)


def _can_view_cost(role: UserRole) -> bool:
    return role_value(role) in {UserRole.SUPER_ADMIN.value, UserRole.TENANT_ADMIN.value}


def _serialize_variant(variant: ProductVariant, role: UserRole) -> ProductVariantResponse:
    return ProductVariantResponse(
        id=variant.id,
        sku=variant.sku,
        color=variant.color,
        size=variant.size,
        barcode=variant.barcode,
        cost_price=variant.cost_price if _can_view_cost(role) else None,
        selling_price=variant.selling_price,
        liquidation_floor_price=variant.liquidation_floor_price,
    )


def _serialize_product(product: Product, variants: list[ProductVariant], role: UserRole) -> ProductResponse:
    return ProductResponse(
        id=product.id,
        tenant_id=product.tenant_id,
        name=product.name,
        category=product.category,
        unit_of_measure=product.unit_of_measure,
        is_active=product.is_active,
        variants=[_serialize_variant(variant, role) for variant in variants],
    )


async def create_warehouse(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request: WarehouseCreateRequest,
) -> WarehouseResponse:
    warehouse = Warehouse(tenant_id=tenant_id, name=request.name, location=request.location)
    try:
        session.add(warehouse)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return WarehouseResponse.model_validate(warehouse)


async def update_warehouse(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    request: WarehouseUpdateRequest,
) -> WarehouseResponse:
    warehouse = (
        await session.exec(
            select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.tenant_id == tenant_id)
        )
    ).one_or_none()
    if warehouse is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Warehouse not found.")

    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(warehouse, field, value)

    session.add(warehouse)
    await session.commit()
    await session.refresh(warehouse)
    return WarehouseResponse.model_validate(warehouse)


async def deactivate_warehouse(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    warehouse_id: uuid.UUID,
) -> WarehouseResponse:
    warehouse = (
        await session.exec(
            select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.tenant_id == tenant_id)
        )
    ).one_or_none()
    if warehouse is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Warehouse not found.")
    warehouse.is_active = False
    session.add(warehouse)
    await session.commit()
    await session.refresh(warehouse)
    return WarehouseResponse.model_validate(warehouse)


async def list_warehouses(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    cursor: str | None,
    limit: int,
) -> WarehousePageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [Warehouse.tenant_id == tenant_id, Warehouse.is_active.is_(True)]
    if decoded_cursor is not None:
        filters.append(Warehouse.id > decoded_cursor)

    total_count = (await session.exec(select(func.count(Warehouse.id)).where(*filters))).one()
    warehouses = (
        await session.exec(
            select(Warehouse)
            .where(*filters)
            .order_by(Warehouse.id.asc())
            .limit(limit + 1)
        )
    ).all()
    has_more = len(warehouses) > limit
    warehouses = warehouses[:limit]
    next_cursor = encode_cursor(warehouses[-1].id) if has_more and warehouses else None
    return WarehousePageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=[WarehouseResponse.model_validate(warehouse) for warehouse in warehouses],
    )


async def create_product(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    request: ProductCreateRequest,
    current_role: UserRole,
) -> ProductResponse:
    product = Product(
        tenant_id=tenant_id,
        name=request.name,
        category=request.category,
        unit_of_measure=request.unit_of_measure,
    )
    variants = [
        ProductVariant(
            tenant_id=tenant_id,
            product_id=product.id,
            sku=variant.sku,
            color=variant.color,
            size=variant.size,
            barcode=variant.barcode,
            cost_price=variant.cost_price,
            selling_price=variant.selling_price,
            liquidation_floor_price=variant.liquidation_floor_price,
        )
        for variant in request.variants
    ]

    try:
        session.add(product)
        for variant in variants:
            session.add(variant)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppException(
            status_code=409,
            code="SKU_CONFLICT",
            message="One or more SKU values already exist.",
        ) from exc
    except Exception:
        await session.rollback()
        raise

    return _serialize_product(product, variants, current_role)


async def update_product(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    request: ProductUpdateRequest,
    current_role: UserRole,
) -> ProductResponse:
    product = (
        await session.exec(
            select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
        )
    ).one_or_none()
    if product is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Product not found.")

    updates = request.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(product, field, value)

    session.add(product)
    await session.commit()
    await session.refresh(product)

    variants = (
        await session.exec(
            select(ProductVariant)
            .where(ProductVariant.product_id == product.id, ProductVariant.tenant_id == tenant_id)
            .order_by(ProductVariant.sku.asc())
        )
    ).all()
    return _serialize_product(product, variants, current_role)


async def update_product_variant(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    variant_id: uuid.UUID,
    request: ProductVariantUpdateRequest,
    current_role: UserRole,
) -> ProductVariantResponse:
    variant = (
        await session.exec(
            select(ProductVariant).where(
                ProductVariant.id == variant_id,
                ProductVariant.tenant_id == tenant_id,
            )
        )
    ).one_or_none()
    if variant is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Variant not found.")

    updates = request.model_dump(exclude_unset=True)
    selling_price = updates.get("selling_price", variant.selling_price)
    floor_price = updates.get("liquidation_floor_price", variant.liquidation_floor_price)
    if floor_price > selling_price:
        raise AppException(
            status_code=400,
            code="INVALID_PRICE",
            message="liquidation_floor_price cannot be greater than selling_price.",
        )

    for field, value in updates.items():
        setattr(variant, field, value)

    try:
        session.add(variant)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppException(
            status_code=409,
            code="VARIANT_CONFLICT",
            message="Variant barcode or SKU conflicts with an existing variant.",
        ) from exc
    await session.refresh(variant)
    return _serialize_variant(variant, current_role)


async def deactivate_product(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    current_role: UserRole,
) -> ProductResponse:
    product = (
        await session.exec(
            select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
        )
    ).one_or_none()
    if product is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Product not found.")

    product.is_active = False
    session.add(product)
    await session.commit()
    await session.refresh(product)

    variants = (
        await session.exec(
            select(ProductVariant)
            .where(ProductVariant.product_id == product.id, ProductVariant.tenant_id == tenant_id)
            .order_by(ProductVariant.sku.asc())
        )
    ).all()
    return _serialize_product(product, variants, current_role)


async def list_products(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    current_role: UserRole,
    cursor: str | None,
    limit: int,
    category: str | None,
    is_active: bool | None,
) -> ProductPageResponse:
    decoded_cursor = decode_cursor(cursor)
    filters = [Product.tenant_id == tenant_id]
    if decoded_cursor is not None:
        filters.append(Product.id > decoded_cursor)
    if category:
        filters.append(Product.category == category)
    if is_active is not None:
        filters.append(Product.is_active == is_active)

    total_count = (await session.exec(select(func.count(Product.id)).where(*filters))).one()

    products = (
        await session.exec(
            select(Product)
            .where(*filters)
            .order_by(Product.id.asc())
            .limit(limit + 1)
        )
    ).all()

    has_more = len(products) > limit
    products = products[:limit]
    next_cursor = encode_cursor(products[-1].id) if has_more and products else None

    product_ids = [product.id for product in products]
    variants = []
    if product_ids:
        variants = (
            await session.exec(
                select(ProductVariant)
                .where(
                    ProductVariant.tenant_id == tenant_id,
                    ProductVariant.product_id.in_(product_ids),
                )
                .order_by(ProductVariant.sku.asc())
            )
        ).all()

    grouped_variants: dict[uuid.UUID, list[ProductVariant]] = defaultdict(list)
    for variant in variants:
        grouped_variants[variant.product_id].append(variant)

    data = [
        _serialize_product(product, grouped_variants.get(product.id, []), current_role)
        for product in products
    ]
    return ProductPageResponse(
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
        data=data,
    )


async def get_product(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    current_role: UserRole,
) -> ProductResponse:
    product = (
        await session.exec(
            select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
        )
    ).one_or_none()
    if product is None:
        raise AppException(status_code=404, code="NOT_FOUND", message="Product not found.")

    variants = (
        await session.exec(
            select(ProductVariant)
            .where(ProductVariant.product_id == product.id, ProductVariant.tenant_id == tenant_id)
            .order_by(ProductVariant.sku.asc())
        )
    ).all()
    return _serialize_product(product, variants, current_role)
