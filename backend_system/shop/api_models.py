"""Pydantic request/response models for the shop API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Traffic / sessions
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    anonymous_id: Optional[str] = Field(None, description="Existing visitor cookie, if any")
    source: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None
    channel: Optional[str] = None
    device: Optional[str] = "desktop"
    country: Optional[str] = "US"
    landing_page: Optional[str] = "/"


class LoginRequest(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    auto_register: bool = Field(True, description="Create the user if the email is unknown")


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

class CartCreate(BaseModel):
    session_id: str
    currency: str = "USD"


class CartItemAdd(BaseModel):
    variant_id: str
    quantity: int = Field(1, ge=1, le=99)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class OrderCreate(BaseModel):
    cart_id: str


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

class PaymentCreate(BaseModel):
    order_id: str
    method: str = Field("credit_card")
    gateway: str = "stripe"


class PaymentFail(BaseModel):
    failure_reason: Optional[str] = "card_declined"


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class SessionResponse(BaseModel):
    session_id: str
    anonymous_id: str
    user_id: Optional[str] = None
    source: Optional[str] = None
    channel: Optional[str] = None
    started_at: datetime


class IdentityResponse(BaseModel):
    anonymous_id: str
    user_id: str
    linked_at: datetime
    link_source: str


class CartItemResponse(BaseModel):
    variant_id: str
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    variant_name: Optional[str] = None
    quantity: int
    unit_price: Decimal
    unit_discounted_price: Decimal
    line_total: Decimal
    currency: str


class CartResponse(BaseModel):
    cart_id: str
    session_id: str
    user_id: Optional[str] = None
    status: str
    currency: str
    item_count: int
    subtotal: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    total: Decimal
    lucky_roll_id: Optional[str] = None
    converted_order_id: Optional[str] = None
    items: list[CartItemResponse] = Field(default_factory=list)


class LuckyRollResponse(BaseModel):
    roll_id: str
    scope_type: str
    scope_id: str
    roll_date: date
    rolled_value: int
    won: bool
    discount_pct: Decimal
    cart_id: str
    message: str


class OrderItemResponse(BaseModel):
    variant_id: str
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    variant_name: Optional[str] = None
    quantity: int
    unit_price: Decimal
    unit_discounted_price: Decimal
    line_total: Decimal
    currency: str


class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    cart_id: Optional[str] = None
    status: str
    currency: str
    item_count: int
    subtotal: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    discount_reason: Optional[str] = None
    tax_amount: Decimal
    shipping_amount: Decimal
    total_amount: Decimal
    created_at: datetime
    items: list[OrderItemResponse] = Field(default_factory=list)


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    user_id: Optional[str] = None
    attempt_no: int
    amount: Decimal
    currency: str
    method: str
    status: str
    gateway: Optional[str] = None
    gateway_transaction_ref: Optional[str] = None
    gateway_fee: Optional[Decimal] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
