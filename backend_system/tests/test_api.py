"""Integration tests for the shop API.

These run against a local Postgres on 127.0.0.1:5432 using a dedicated
`shop_test` database. They are skipped automatically if Postgres is not
reachable.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from shop import pg_schema

HOST = "127.0.0.1"
PORT = 5432
USER = "shop"
PASSWORD = "shop"
TEST_DB = "shop_test"


def _admin_conn():
    return psycopg.connect(host=HOST, port=PORT, dbname="postgres",
                           user=USER, password=PASSWORD, connect_timeout=3,
                           autocommit=True)


def _postgres_available() -> bool:
    try:
        conn = _admin_conn()
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason="local Postgres not reachable on 127.0.0.1:5432",
)


@pytest.fixture(scope="module")
def client():
    admin = _admin_conn()
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
        cur.execute(f'CREATE DATABASE "{TEST_DB}"')
    admin.close()

    conn = psycopg.connect(host=HOST, port=PORT, dbname=TEST_DB,
                           user=USER, password=PASSWORD, autocommit=True)
    pg_schema.reset_schema(conn)
    conn.close()

    from shop.api import create_app

    app = create_app(host=HOST, port=PORT, dbname=TEST_DB,
                     user=USER, password=PASSWORD)
    with TestClient(app) as test_client:
        yield test_client
    app.state.shop_repository.close()

    admin = _admin_conn()
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
    admin.close()


def _seed_variant(client) -> dict:
    """Insert one catalog variant directly through the API's repository."""
    repo = client.app.state.shop_repository
    from datetime import datetime
    from decimal import Decimal

    variant = {
        "variant_id": f"v_{uuid.uuid4().hex[:8]}",
        "product_id": "p_test",
        "category_id": "electronics",
        "product_name": "Test Earbuds",
        "variant_name": "Black",
        "sku": "TEST-01",
        "attributes": {"color": "Black"},
        "price": Decimal("100.00"),
        "discounted_price": Decimal("80.00"),
        "currency": "USD",
        "is_active": True,
        "created_at": datetime.utcnow(),
    }
    repo.insert("variants_by_product", {
        "product_id": variant["product_id"],
        "variant_id": variant["variant_id"],
        "category_id": variant["category_id"],
        "product_name": variant["product_name"],
        "variant_name": variant["variant_name"],
        "sku": variant["sku"],
        "attributes": variant["attributes"],
        "price": variant["price"],
        "discounted_price": variant["discounted_price"],
        "currency": variant["currency"],
        "is_active": True,
        "created_at": variant["created_at"],
    })
    repo.insert("product_item_by_id", variant)
    return variant


def test_full_checkout_flow(client):
    # 1. start a session (guest)
    session = client.post("/api/v1/sessions", json={"channel": "direct"}).json()
    assert "session_id" in session
    session_id = session["session_id"]

    # 2. guest creates a cart
    cart = client.post("/api/v1/carts", json={"session_id": session_id, "currency": "USD"}).json()
    cart_id = cart["cart_id"]
    assert cart["status"] == "active"

    # 3. add an item
    variant = _seed_variant(client)
    cart = client.post(
        f"/api/v1/carts/{cart_id}/items",
        json={"variant_id": variant["variant_id"], "quantity": 2},
    ).json()
    assert cart["item_count"] == 1
    assert len(cart["items"]) == 1

    # 4. checkout without login is rejected (no guest checkout)
    resp = client.post("/api/v1/orders", json={"cart_id": cart_id})
    assert resp.status_code == 401

    # 5. log in (register) -> stitches anonymous_id to user_id
    login = client.post(
        f"/api/v1/sessions/{session_id}/login",
        json={"email": f"u_{uuid.uuid4().hex[:6]}@example.com", "auto_register": True},
    ).json()
    assert "user_id" in login

    # 6. place the order from the adopted cart
    order = client.post("/api/v1/orders", json={"cart_id": cart_id}).json()
    assert order["status"] == "pending"
    assert order["item_count"] == 1
    assert order["subtotal"] == "160.00"  # 2 x 80.00 discounted price
    assert len(order["items"]) == 1

    # 7. pay for it
    payment = client.post(
        "/api/v1/payments", json={"order_id": order["order_id"], "method": "credit_card"}
    ).json()
    assert payment["status"] == "pending"
    payment_id = payment["payment_id"]

    assert client.post(f"/api/v1/payments/{payment_id}/process").json()["status"] == "processing"
    completed = client.post(f"/api/v1/payments/{payment_id}/complete").json()
    assert completed["status"] == "completed"

    # 8. the order reflects completion
    refreshed = client.get(f"/api/v1/orders/{order['order_id']}").json()
    assert refreshed["status"] == "completed"

    # 9. refund
    refunded = client.post(f"/api/v1/payments/{payment_id}/refund").json()
    assert refunded["status"] == "refunded"
    assert client.get(f"/api/v1/orders/{order['order_id']}").json()["status"] == "refunded"


def test_lucky_check_is_once_per_day(client):
    session = client.post("/api/v1/sessions", json={"channel": "direct"}).json()
    cart = client.post(
        "/api/v1/carts", json={"session_id": session["session_id"], "currency": "USD"}
    ).json()
    cart_id = cart["cart_id"]

    first = client.post(f"/api/v1/carts/{cart_id}/lucky-check")
    assert first.status_code == 200
    assert "won" in first.json()

    second = client.post(f"/api/v1/carts/{cart_id}/lucky-check")
    assert second.status_code == 409


def test_cannot_checkout_empty_cart(client):
    session = client.post("/api/v1/sessions", json={"channel": "direct"}).json()
    cart = client.post(
        "/api/v1/carts", json={"session_id": session["session_id"], "currency": "USD"}
    ).json()
    client.post(
        f"/api/v1/sessions/{session['session_id']}/login",
        json={"email": f"e_{uuid.uuid4().hex[:6]}@example.com", "auto_register": True},
    )
    resp = client.post("/api/v1/orders", json={"cart_id": cart["cart_id"]})
    assert resp.status_code == 400


def test_missing_entities_return_404(client):
    assert client.get("/api/v1/orders/nope").status_code == 404
    assert client.get("/api/v1/payments/nope").status_code == 404
    assert client.get("/api/v1/carts/nope").status_code == 404
    assert client.get("/api/v1/variants/nope").status_code == 404
