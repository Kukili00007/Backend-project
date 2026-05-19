"""Initial LeanStock schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False, server_default="starter"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"], unique=False)
    op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="analyst"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False)
    op.create_index("ix_users_tenant_email", "users", ["tenant_id", "email"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False, server_default="pcs"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"], unique=False)

    op.create_table(
        "warehouses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_warehouses_tenant_id", "warehouses", ["tenant_id"], unique=False)

    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("size", sa.String(length=50), nullable=True),
        sa.Column("barcode", sa.String(length=50), nullable=True),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("selling_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("liquidation_floor_price", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("cost_price >= 0", name="ck_variants_cost_price_non_negative"),
        sa.CheckConstraint("selling_price >= 0", name="ck_variants_selling_price_non_negative"),
        sa.CheckConstraint(
            "liquidation_floor_price >= 0",
            name="ck_variants_liquidation_floor_non_negative",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_variants_barcode", "product_variants", ["barcode"], unique=False)
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"], unique=False)
    op.create_index("ix_product_variants_sku", "product_variants", ["sku"], unique=True)
    op.create_index("ix_product_variants_tenant_id", "product_variants", ["tenant_id"], unique=False)

    op.create_table(
        "inventory_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reorder_threshold", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_sold_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decay_status", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("decay_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_quantity_non_negative"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("variant_id", "warehouse_id", name="uq_variant_warehouse"),
    )
    op.create_index("ix_inventory_items_variant_id", "inventory_items", ["variant_id"], unique=False)
    op.create_index(
        "ix_inventory_items_warehouse_id", "inventory_items", ["warehouse_id"], unique=False
    )
    op.create_index(
        "ix_inventory_tenant_warehouse", "inventory_items", ["tenant_id", "warehouse_id"], unique=False
    )
    op.create_index(
        "ix_inventory_last_sold",
        "inventory_items",
        ["tenant_id", "last_sold_at"],
        unique=False,
        postgresql_where=sa.column("decay_status") == "normal",
    )

    op.create_table(
        "stock_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confirmed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_stock_transfers_quantity_positive"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["from_warehouse_id"], ["warehouses.id"]),
        sa.ForeignKeyConstraint(["to_warehouse_id"], ["warehouses.id"]),
        sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
        sa.ForeignKeyConstraint(["initiated_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_transfers_request_id", "stock_transfers", ["request_id"], unique=True)
    op.create_index("ix_stock_transfers_tenant_id", "stock_transfers", ["tenant_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_tenant_created", "audit_logs", ["tenant_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_audit_tenant_created", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_stock_transfers_tenant_id", table_name="stock_transfers")
    op.drop_index("ix_stock_transfers_request_id", table_name="stock_transfers")
    op.drop_table("stock_transfers")

    op.drop_index("ix_inventory_last_sold", table_name="inventory_items")
    op.drop_index("ix_inventory_tenant_warehouse", table_name="inventory_items")
    op.drop_index("ix_inventory_items_warehouse_id", table_name="inventory_items")
    op.drop_index("ix_inventory_items_variant_id", table_name="inventory_items")
    op.drop_table("inventory_items")

    op.drop_index("ix_product_variants_tenant_id", table_name="product_variants")
    op.drop_index("ix_product_variants_sku", table_name="product_variants")
    op.drop_index("ix_product_variants_product_id", table_name="product_variants")
    op.drop_index("ix_product_variants_barcode", table_name="product_variants")
    op.drop_table("product_variants")

    op.drop_index("ix_warehouses_tenant_id", table_name="warehouses")
    op.drop_table("warehouses")

    op.drop_index("ix_products_tenant_id", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_users_tenant_email", table_name="users")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_tenants_slug", table_name="tenants")
    op.drop_index("ix_tenants_name", table_name="tenants")
    op.drop_table("tenants")
