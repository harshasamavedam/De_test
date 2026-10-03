"""Cassandra repository for the shop API.

Reuses the prepared INSERT statements and column ordering from
`shop.writer`, and adds the read/update queries the API needs. Every query is
partition-key based to stay in line with the query-first model.
"""

from __future__ import annotations

from typing import Any

from cassandra.cluster import Cluster
from cassandra.query import dict_factory

from . import schema
from .writer import ROW_ORDER


class ShopRepository:
    def __init__(self, host: str = "127.0.0.1", port: int = 9042, keyspace: str = "shop"):
        self.host = host
        self.port = port
        self.keyspace = keyspace
        self.cluster = None
        self.session = None
        self._inserts: dict[str, Any] = {}
        self._updates: dict[str, Any] = {}

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> None:
        self.cluster = Cluster([self.host], port=self.port)
        self.session = self.cluster.connect(self.keyspace)
        self.session.row_factory = dict_factory
        for table, cql in schema.INSERTS.items():
            self._inserts[table] = self.session.prepare(cql)
        for name, cql in UPDATES.items():
            self._updates[name] = self.session.prepare(cql)

    def close(self) -> None:
        if self.cluster:
            self.cluster.shutdown()

    # -- generic -----------------------------------------------------------
    def insert(self, table: str, entity: dict) -> None:
        order = ROW_ORDER[table]
        self.session.execute(self._inserts[table], [entity.get(col) for col in order])

    def insert_many(self, table: str, entities: list[dict]) -> None:
        for entity in entities:
            self.insert(table, entity)

    def update(self, name: str, values: list) -> None:
        self.session.execute(self._updates[name], values)

    def one(self, cql: str, params: tuple = ()) -> dict | None:
        return self.session.execute(cql, params).one()

    def many(self, cql: str, params: tuple = ()) -> list[dict]:
        return list(self.session.execute(cql, params))

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
        self.session.execute(
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
        UPDATE carts SET status = ?, item_count = ?, subtotal = ?,
            discount_pct = ?, discount_amount = ?, total = ?,
            lucky_roll_id = ?, converted_order_id = ?, updated_at = ?
        WHERE cart_id = ?
    """,
    "cart_session_status": """
        UPDATE cart_by_session SET user_id = ?, status = ?, updated_at = ?
        WHERE session_id = ?
    """,
    "session_user": "UPDATE sessions SET user_id = ? WHERE session_id = ?",
    "order_status": "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
    "order_status_by_user": """
        UPDATE orders_by_user SET status = ?
        WHERE user_id = ? AND created_at = ? AND order_id = ?
    """,
    "payment_status": """
        UPDATE payments SET status = ?, processed_at = ?, completed_at = ?,
            failed_at = ?, refunded_at = ?, failure_reason = ?
        WHERE payment_id = ?
    """,
    "payment_status_by_order": """
        UPDATE payments_by_order SET status = ?, completed_at = ?, failed_at = ?
        WHERE order_id = ? AND attempt_no = ?
    """,
}
