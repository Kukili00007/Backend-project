from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.procurement import PurchaseOrderStatus
from app.models.transfer import TransferStatus
from app.models.user import UserRole

PASSWORD_RULE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{8,}$")
SLUG_RULE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ErrorResponse(BaseModel):
    code: str = Field(examples=["INSUFFICIENT_STOCK"])
    message: str = Field(examples=["Only 3 units available, 5 requested"])
    details: dict | None = None


class MessageResponse(BaseModel):
    message: str = Field(examples=["If the account exists, an email has been queued."])


class LoginRequest(BaseModel):
    email: EmailStr = Field(examples=["admin@arzanshop.kz"])
    password: str = Field(min_length=8, examples=["Secur3P@ss!"])


class RegisterRequest(BaseModel):
    email: EmailStr = Field(examples=["owner@arzanshop.kz"])
    password: str = Field(min_length=8, examples=["Secur3P@ss!"])
    name: str = Field(min_length=2, max_length=255, examples=["Aibek Dzhaksybekov"])
    role: UserRole = Field(default=UserRole.TENANT_ADMIN, examples=["tenant_admin"])
    tenant_name: str | None = Field(default=None, max_length=255, examples=["Arzan Shop"])
    tenant_slug: str | None = Field(default=None, max_length=100, examples=["arzan-shop"])

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not PASSWORD_RULE.match(value):
            raise ValueError(
                "Password must include upper/lowercase letters, a number, and a special character."
            )
        return value

    @field_validator("tenant_slug")
    @classmethod
    def validate_slug(cls, value: str | None) -> str | None:
        if value and not SLUG_RULE.match(value):
            raise ValueError("tenant_slug must be lowercase letters, numbers, and hyphens only.")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str = Field(examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."])


class LogoutRequest(RefreshRequest):
    pass


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=32, examples=["email-verify-token-from-link"])
    email: EmailStr | None = Field(default=None, examples=["owner@arzanshop.kz"])


class ResendVerificationRequest(BaseModel):
    email: EmailStr = Field(examples=["owner@arzanshop.kz"])


class PasswordResetRequest(BaseModel):
    email: EmailStr = Field(examples=["owner@arzanshop.kz"])


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=32, examples=["password-reset-token-from-link"])
    new_password: str = Field(min_length=8, examples=["N3wSecur3P@ss!"])

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not PASSWORD_RULE.match(value):
            raise ValueError(
                "Password must include upper/lowercase letters, a number, and a special character."
            )
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    name: str
    role: UserRole
    is_active: bool
    email_verified_at: datetime | None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(examples=[1800])


class WarehouseCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    location: str | None = Field(default=None, max_length=500)


class WarehouseUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    location: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    location: str | None
    is_active: bool


class WarehousePageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[WarehouseResponse]


class ProductVariantCreateRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=100, examples=["TSHIRT-RED-L"])
    color: str | None = Field(default=None, max_length=50)
    size: str | None = Field(default=None, max_length=50)
    barcode: str | None = Field(default=None, max_length=50)
    cost_price: Decimal = Field(ge=0, decimal_places=2, examples=[2100.00])
    selling_price: Decimal = Field(ge=0, decimal_places=2, examples=[4990.00])
    liquidation_floor_price: Decimal = Field(ge=0, decimal_places=2, examples=[2990.00])

    @field_validator("liquidation_floor_price")
    @classmethod
    def validate_floor_price(cls, value: Decimal, info) -> Decimal:
        selling_price = info.data.get("selling_price")
        if selling_price is not None and value > selling_price:
            raise ValueError("liquidation_floor_price cannot be greater than selling_price.")
        return value


class ProductCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255, examples=["Classic T-Shirt"])
    category: str | None = Field(default=None, max_length=100, examples=["Clothing"])
    unit_of_measure: Literal["pcs", "kg", "pack"] = "pcs"
    variants: list[ProductVariantCreateRequest] = Field(min_length=1)


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    unit_of_measure: Literal["pcs", "kg", "pack"] | None = None
    is_active: bool | None = None


class ProductVariantUpdateRequest(BaseModel):
    color: str | None = Field(default=None, max_length=50)
    size: str | None = Field(default=None, max_length=50)
    barcode: str | None = Field(default=None, max_length=50)
    cost_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    selling_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    liquidation_floor_price: Decimal | None = Field(default=None, ge=0, decimal_places=2)


class ProductVariantResponse(BaseModel):
    id: uuid.UUID
    sku: str
    color: str | None = None
    size: str | None = None
    barcode: str | None = None
    cost_price: Decimal | None = None
    selling_price: Decimal
    liquidation_floor_price: Decimal


class ProductResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    category: str | None
    unit_of_measure: str
    is_active: bool
    variants: list[ProductVariantResponse]


class ProductPageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[ProductResponse]


class InventoryAdjustRequest(BaseModel):
    variant_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity_delta: int = Field(examples=[-3])
    reason: Literal["damage", "theft", "surplus", "count_correction", "other"]
    note: str | None = Field(default=None, max_length=500)


class ReservationRequest(BaseModel):
    variant_id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: int = Field(ge=1)
    order_reference: str = Field(min_length=1, max_length=100)


class ReservationResponse(BaseModel):
    reservation_id: str
    expires_at: datetime


class InventoryVariantView(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    color: str | None = None
    size: str | None = None
    barcode: str | None = None
    selling_price: Decimal
    liquidation_floor_price: Decimal
    cost_price: Decimal | None = None


class InventoryItemResponse(BaseModel):
    id: uuid.UUID
    warehouse_id: uuid.UUID
    quantity: int
    reorder_threshold: int
    is_low_stock: bool
    decay_status: Literal["normal", "liquidating"]
    current_price: Decimal
    discount_pct: Decimal
    last_sold_at: datetime | None
    variant: InventoryVariantView


class InventoryPageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[InventoryItemResponse]


class ForecastSuggestionResponse(BaseModel):
    inventory_item_id: uuid.UUID
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    sku: str
    product_name: str
    current_quantity: int
    reorder_threshold: int
    forecast_window_days: int
    lead_time_days: int
    observed_outgoing_units: int
    average_daily_demand: Decimal
    recommended_reorder_quantity: int
    urgency: Literal["none", "watch", "reorder_now"]


class ForecastPageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[ForecastSuggestionResponse]


class TransferCreateRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=100, examples=["txfr-20260413-001"])
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=500)


class TransferConfirmRequest(BaseModel):
    received_quantity: int | None = Field(default=None, ge=1)


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: str
    tenant_id: uuid.UUID
    status: TransferStatus
    from_warehouse_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int
    note: str | None
    initiated_by: uuid.UUID
    confirmed_by: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None


class TransferPageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[TransferResponse]


class EmailJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_email: EmailStr
    subject: str
    purpose: str
    status: str
    retry_count: int
    error_message: str | None
    created_at: datetime
    sent_at: datetime | None


class EmailJobPageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[EmailJobResponse]


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    before_state: dict | None = None
    after_state: dict | None = None
    created_at: datetime


class AuditLogPageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[AuditLogResponse]


class DebugTokenRequest(BaseModel):
    email: EmailStr = Field(examples=["owner@arzanshop.kz"])
    admin_secret: str = Field(min_length=32, examples=["leanstock-demo-email-verify-2026"])


class DebugTokenResponse(BaseModel):
    token: str
    email: EmailStr
    hint: str = "POST /auth/verify-email  { \"token\": \"<token>\", \"email\": \"<email>\" }"


class DecayRunResponse(BaseModel):
    marked_liquidating: int
    discounted: int


class SupplierCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255, examples=["Almaty Textile Supply"])
    contact_email: EmailStr | None = Field(default=None, examples=["orders@supplier.kz"])
    phone: str | None = Field(default=None, max_length=50, examples=["+77001234567"])
    lead_time_days: int = Field(default=7, ge=1, le=120)


class SupplierUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    contact_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    lead_time_days: int | None = Field(default=None, ge=1, le=120)
    is_active: bool | None = None


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    contact_email: EmailStr | None
    phone: str | None
    lead_time_days: int
    is_active: bool
    created_at: datetime


class SupplierPageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[SupplierResponse]


class PurchaseOrderCreateRequest(BaseModel):
    po_number: str = Field(min_length=1, max_length=100, examples=["PO-2026-001"])
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, examples=[25])
    expected_unit_cost: Decimal = Field(ge=0, decimal_places=2, examples=[2100.00])


class PurchaseOrderReceiveRequest(BaseModel):
    received_quantity: int | None = Field(default=None, ge=1)


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    po_number: str
    supplier_id: uuid.UUID
    warehouse_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int
    expected_unit_cost: Decimal
    status: PurchaseOrderStatus
    created_by: uuid.UUID
    submitted_at: datetime | None
    confirmed_at: datetime | None
    received_at: datetime | None
    created_at: datetime


class PurchaseOrderPageResponse(BaseModel):
    next_cursor: str | None
    has_more: bool
    total_count: int
    data: list[PurchaseOrderResponse]
