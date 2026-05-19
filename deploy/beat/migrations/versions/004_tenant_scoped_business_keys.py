"""Scope SKU and transfer request keys by tenant."""

from __future__ import annotations

from alembic import op

revision = "004_tenant_scoped_business_keys"
down_revision = "003_suppliers_purchase_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_product_variants_sku", table_name="product_variants")
    op.create_index("ix_product_variants_sku", "product_variants", ["sku"], unique=False)
    op.create_unique_constraint(
        "uq_product_variant_tenant_sku",
        "product_variants",
        ["tenant_id", "sku"],
    )

    op.drop_index("ix_stock_transfers_request_id", table_name="stock_transfers")
    op.create_index(
        "ix_stock_transfers_request_id",
        "stock_transfers",
        ["request_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_transfer_tenant_request",
        "stock_transfers",
        ["tenant_id", "request_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_transfer_tenant_request",
        "stock_transfers",
        type_="unique",
    )
    op.drop_index("ix_stock_transfers_request_id", table_name="stock_transfers")
    op.create_index(
        "ix_stock_transfers_request_id",
        "stock_transfers",
        ["request_id"],
        unique=True,
    )

    op.drop_constraint(
        "uq_product_variant_tenant_sku",
        "product_variants",
        type_="unique",
    )
    op.drop_index("ix_product_variants_sku", table_name="product_variants")
    op.create_index(
        "ix_product_variants_sku",
        "product_variants",
        ["sku"],
        unique=True,
    )
