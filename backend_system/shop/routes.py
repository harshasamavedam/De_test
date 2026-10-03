"""FastAPI routes for the shop commerce platform.

All endpoints operate on the `shop` keyspace. Checkout enforces login (no guest
checkout), and the Lucky Check discount is frozen onto the cart.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from . import api_models as m
from .service import ShopError, ShopService


router = APIRouter(prefix="/api/v1")


def get_service(request: Request) -> ShopService:
    return request.app.state.shop_service


def _handle(exc: ShopError):
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ---------------------------------------------------------------------------
# Traffic / sessions
# ---------------------------------------------------------------------------

@router.post("/sessions", response_model=m.SessionResponse, tags=["traffic"])
def create_session(payload: m.SessionCreate, service: ShopService = Depends(get_service)):
    return service.create_session(payload)


@router.get("/sessions/{session_id}", tags=["traffic"])
def get_session(session_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.get_session(session_id)
    except ShopError as exc:
        _handle(exc)


@router.post("/sessions/{session_id}/login", tags=["traffic"])
def login(session_id: str, payload: m.LoginRequest, service: ShopService = Depends(get_service)):
    try:
        return service.login(session_id, payload)
    except ShopError as exc:
        _handle(exc)


@router.get("/sessions/{session_id}/events", tags=["traffic"])
def list_events(session_id: str, service: ShopService = Depends(get_service)):
    try:
        service.get_session(session_id)
    except ShopError as exc:
        _handle(exc)
    return service.repo.list_events(session_id)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

@router.get("/categories", tags=["catalog"])
def list_categories(service: ShopService = Depends(get_service)):
    return service.repo.list_categories()


@router.get("/categories/{category_id}/products", tags=["catalog"])
def list_products(category_id: str, service: ShopService = Depends(get_service)):
    return service.repo.list_products(category_id)


@router.get("/products/{product_id}/variants", tags=["catalog"])
def list_variants(product_id: str, service: ShopService = Depends(get_service)):
    return service.repo.list_variants(product_id)


@router.get("/variants/{variant_id}", tags=["catalog"])
def get_variant(variant_id: str, service: ShopService = Depends(get_service)):
    variant = service.repo.get_variant(variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail=f"variant {variant_id} not found")
    return variant


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

@router.post("/carts", response_model=m.CartResponse, tags=["cart"])
def create_cart(payload: m.CartCreate, service: ShopService = Depends(get_service)):
    try:
        cart = service.create_cart(payload)
    except ShopError as exc:
        _handle(exc)
    return service.get_cart(cart["cart_id"])


@router.get("/carts/{cart_id}", response_model=m.CartResponse, tags=["cart"])
def get_cart(cart_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.get_cart(cart_id)
    except ShopError as exc:
        _handle(exc)


@router.post("/carts/{cart_id}/items", response_model=m.CartResponse, tags=["cart"])
def add_cart_item(cart_id: str, payload: m.CartItemAdd, service: ShopService = Depends(get_service)):
    try:
        return service.add_cart_item(cart_id, payload)
    except ShopError as exc:
        _handle(exc)


@router.delete("/carts/{cart_id}/items/{variant_id}", response_model=m.CartResponse, tags=["cart"])
def remove_cart_item(cart_id: str, variant_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.remove_cart_item(cart_id, variant_id)
    except ShopError as exc:
        _handle(exc)


@router.post("/carts/{cart_id}/lucky-check", response_model=m.LuckyRollResponse, tags=["discount"])
def lucky_check(cart_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.lucky_check(cart_id)
    except ShopError as exc:
        _handle(exc)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@router.post("/orders", response_model=m.OrderResponse, tags=["orders"])
def create_order(payload: m.OrderCreate, service: ShopService = Depends(get_service)):
    try:
        return service.create_order(payload)
    except ShopError as exc:
        _handle(exc)


@router.get("/orders/{order_id}", response_model=m.OrderResponse, tags=["orders"])
def get_order(order_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.get_order(order_id)
    except ShopError as exc:
        _handle(exc)


@router.get("/users/{user_id}/orders", tags=["orders"])
def list_user_orders(user_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.list_user_orders(user_id)
    except ShopError as exc:
        _handle(exc)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@router.post("/payments", response_model=m.PaymentResponse, tags=["payments"])
def create_payment(payload: m.PaymentCreate, service: ShopService = Depends(get_service)):
    try:
        return service.create_payment(payload)
    except ShopError as exc:
        _handle(exc)


@router.get("/payments/{payment_id}", response_model=m.PaymentResponse, tags=["payments"])
def get_payment(payment_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.get_payment(payment_id)
    except ShopError as exc:
        _handle(exc)


@router.post("/payments/{payment_id}/process", response_model=m.PaymentResponse, tags=["payments"])
def process_payment(payment_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.process_payment(payment_id)
    except ShopError as exc:
        _handle(exc)


@router.post("/payments/{payment_id}/complete", response_model=m.PaymentResponse, tags=["payments"])
def complete_payment(payment_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.complete_payment(payment_id)
    except ShopError as exc:
        _handle(exc)


@router.post("/payments/{payment_id}/fail", response_model=m.PaymentResponse, tags=["payments"])
def fail_payment(payment_id: str, payload: m.PaymentFail, service: ShopService = Depends(get_service)):
    try:
        return service.fail_payment(payment_id, payload.failure_reason)
    except ShopError as exc:
        _handle(exc)


@router.post("/payments/{payment_id}/refund", response_model=m.PaymentResponse, tags=["payments"])
def refund_payment(payment_id: str, service: ShopService = Depends(get_service)):
    try:
        return service.refund_payment(payment_id)
    except ShopError as exc:
        _handle(exc)
