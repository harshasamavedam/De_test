"""Postgres repository for the shop API.

Reuses the column ordering from `shop.writer`, and adds the read/update
queries the API needs. Same method surface as the old Cassandra repository,
so `shop.service` is untouched.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from . import pg_schema
from .writer import ROW_ORDER


class ShopRepository:
    def __init__(self, host: str = "127.0.0.1", port: int = 5432,
                 dbname: str = "shop", user: str = "shop",
                 password: str = "shop"):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.user = user
        self.password = password
        self.conn = None

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> None:
        self.conn = psycopg.connect(
            host=self.host, port=self.port, dbname=self.dbname,
            user=self.user, password=self.password,
            connect_timeout=10, autocommit=True,
            row_factory=dict_row,
            # Keep the exploration UI's ad-hoc queries bounded.
            options="-c statement_timeout=10000",
        )

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    # -- generic -----------------------------------------------------------
    def insert(self, table: str, entity: dict) -> None:
        order = ROW_ORDER[table]
        with self.conn.cursor() as cur:
            cur.execute(
                pg_schema.insert_sql(table, order),
                pg_schema.adapt_row([entity.get(col) for col in order]),
            )

    def insert_many(self, table: str, entities: list[dict]) -> None:
        for entity in entities:
            self.insert(table, entity)

    def update(self, name: str, values: list) -> None:
        with self.conn.cursor() as cur:
            cur.execute(UPDATES[name], values)

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def many(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    # -- users -------------------------------------------------------------
    def get_user(self, user_id: str) -> dict | None:
        return self.one("SELECT * FROM users WHERE user_id = %s", (user_id,))

    def get_user_id_by_email(self, email: str) -> str | None:
        row = self.one("SELECT user_id FROM users_by_email WHERE email = %s", (email,))
        return row["user_id"] if row else None

    def list_addresses(self, user_id: str) -> list[dict]:
        return self.many("SELECT * FROM user_addresses WHERE user_id = %s", (user_id,))

    # -- sessions / identity ----------------------------------------------
    def get_session(self, session_id: str) -> dict | None:
        return self.one("SELECT * FROM sessions WHERE session_id = %s", (session_id,))

    def get_sessions_by_anonymous(self, anonymous_id: str) -> list[dict]:
        return self.many(
            "SELECT * FROM sessions_by_anonymous WHERE anonymous_id = %s", (anonymous_id,)
        )

    def get_sessions_by_user(self, user_id: str) -> list[dict]:
        return self.many("SELECT * FROM sessions_by_user WHERE user_id = %s", (user_id,))

    def get_identity(self, anonymous_id: str) -> dict | None:
        return self.one("SELECT * FROM identity_map WHERE anonymous_id = %s", (anonymous_id,))

    def get_identities_by_user(self, user_id: str) -> list[dict]:
        return self.many(
            "SELECT * FROM identity_map_by_user WHERE user_id = %s", (user_id,)
        )

    def list_events(self, session_id: str) -> list[dict]:
        return self.many("SELECT * FROM events WHERE session_id = %s", (session_id,))

    # -- catalog -----------------------------------------------------------
    def list_categories(self) -> list[dict]:
        return self.many("SELECT * FROM categories")

    def list_products(self, category_id: str) -> list[dict]:
        return self.many(
            "SELECT * FROM products_by_category WHERE category_id = %s", (category_id,)
        )

    def list_variants(self, product_id: str) -> list[dict]:
        return self.many(
            "SELECT * FROM variants_by_product WHERE product_id = %s", (product_id,)
        )

    def get_variant(self, variant_id: str) -> dict | None:
        return self.one(
            "SELECT * FROM product_item_by_id WHERE variant_id = %s", (variant_id,)
        )

    # -- cart --------------------------------------------------------------
    def get_cart(self, cart_id: str) -> dict | None:
        return self.one("SELECT * FROM carts WHERE cart_id = %s", (cart_id,))

    def get_cart_by_session(self, session_id: str) -> dict | None:
        return self.one(
            "SELECT * FROM cart_by_session WHERE session_id = %s", (session_id,)
        )

    def get_cart_items(self, cart_id: str) -> list[dict]:
        return self.many("SELECT * FROM cart_items WHERE cart_id = %s", (cart_id,))

    def delete_cart_item(self, cart_id: str, variant_id: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM cart_items WHERE cart_id = %s AND variant_id = %s",
                (cart_id, variant_id),
            )

    def get_carts_by_user(self, user_id: str) -> list[dict]:
        return self.many("SELECT * FROM cart_by_user WHERE user_id = %s", (user_id,))

    # -- lucky roll --------------------------------------------------------
    def get_lucky_roll(self, scope_type: str, scope_id: str, roll_date) -> dict | None:
        return self.one(
            "SELECT * FROM lucky_rolls WHERE scope_type = %s AND scope_id = %s "
            "AND roll_date = %s",
            (scope_type, scope_id, roll_date),
        )

    # -- orders ------------------------------------------------------------
    def get_order(self, order_id: str) -> dict | None:
        return self.one("SELECT * FROM orders WHERE order_id = %s", (order_id,))

    def get_orders_by_user(self, user_id: str) -> list[dict]:
        return self.many("SELECT * FROM orders_by_user WHERE user_id = %s", (user_id,))

    def get_order_items(self, order_id: str) -> list[dict]:
        return self.many("SELECT * FROM order_items WHERE order_id = %s", (order_id,))

    # -- payments ----------------------------------------------------------
    def get_payment(self, payment_id: str) -> dict | None:
        return self.one("SELECT * FROM payments WHERE payment_id = %s", (payment_id,))

    def get_payments_by_order(self, order_id: str) -> list[dict]:
        return self.many(
            "SELECT * FROM payments_by_order WHERE order_id = %s", (order_id,)
        )


UPDATES = {
    "cart_status": """
        UPDATE carts SET status = %s, item_count = %s, subtotal = %s,
            discount_pct = %s, discount_amount = %s, total = %s,
            lucky_roll_id = %s, converted_order_id = %s, updated_at = %s
        WHERE cart_id = %s
    """,
    "cart_session_status": """
        UPDATE cart_by_session SET user_id = %s, status = %s, updated_at = %s
        WHERE session_id = %s
    """,
    "session_user": "UPDATE sessions SET user_id = %s WHERE session_id = %s",
    "order_status": "UPDATE orders SET status = %s, updated_at = %s WHERE order_id = %s",
    "order_status_by_user": """
        UPDATE orders_by_user SET status = %s
        WHERE user_id = %s AND created_at = %s AND order_id = %s
    """,
    "payment_status": """
        UPDATE payments SET status = %s, processed_at = %s, completed_at = %s,
            failed_at = %s, refunded_at = %s, failure_reason = %s
        WHERE payment_id = %s
    """,
    "payment_status_by_order": """
        UPDATE payments_by_order SET status = %s, completed_at = %s, failed_at = %s
        WHERE order_id = %s AND attempt_no = %s
    """,
}
