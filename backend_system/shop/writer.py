"""Postgres writer for the shop simulator.

Wraps connection setup, schema reset and batched per-table inserts. Supports a
dry-run mode that only counts rows, so the generation logic can be validated
without a running database.

Writes are buffered per table and flushed with `executemany` in batches of
`BATCH_ROWS`; `close()` flushes everything. Same interface as the old
Same interface as the old Cassandra writer, so `shop.simulator` is untouched.
"""

from __future__ import annotations

from collections import Counter

import psycopg

from . import pg_schema

# Rows accumulated per table before one executemany round-trip.
BATCH_ROWS = 1000

# Kept for CLI compatibility: bounds the per-table buffers (see Writer).
DEFAULT_MAX_INFLIGHT = 1024

# Column order for every INSERT (must match the entity-dict keys the simulator
# and API build). Shared with `shop.repository`.
ROW_ORDER = {
    "users": ("user_id", "email", "first_name", "last_name", "phone",
              "date_of_birth", "country", "is_active", "created_at", "metadata"),
    "users_by_email": ("email", "user_id", "created_at"),
    "user_addresses": ("user_id", "address_id", "label", "full_name", "line1",
                       "line2", "city", "region", "postal_code", "country",
                       "phone", "is_default", "created_at"),
    "sessions": ("session_id", "anonymous_id", "user_id", "source", "utm_source",
                 "utm_medium", "utm_campaign", "referrer", "channel", "device",
                 "os", "user_agent", "country", "ip_hash", "landing_page",
                 "is_bounce", "started_at", "ended_at", "metadata"),
    "sessions_by_anonymous": ("anonymous_id", "started_at", "session_id",
                              "user_id", "channel", "source", "device", "country"),
    "sessions_by_user": ("user_id", "started_at", "session_id", "anonymous_id",
                         "channel", "source", "device"),
    "identity_map": ("anonymous_id", "user_id", "first_seen", "linked_at",
                     "link_source"),
    "identity_map_by_user": ("user_id", "anonymous_id", "first_seen",
                             "linked_at"),
    "events": ("session_id", "event_at", "event_id", "user_id", "anonymous_id",
               "event_type", "page", "product_id", "variant_id", "cart_id",
               "properties"),
    "categories": ("category_id", "name", "description", "product_count",
                   "created_at"),
    "products_by_category": ("category_id", "product_id", "product_name",
                             "brand", "variant_count", "created_at"),
    "variants_by_product": ("product_id", "variant_id", "category_id",
                            "product_name", "variant_name", "sku", "attributes",
                            "price", "discounted_price", "currency", "is_active",
                            "created_at"),
    "product_item_by_id": ("variant_id", "product_id", "category_id",
                           "product_name", "variant_name", "sku", "attributes",
                           "price", "discounted_price", "currency", "is_active"),
    "carts": ("cart_id", "session_id", "anonymous_id", "user_id", "status",
              "currency", "item_count", "subtotal", "discount_pct",
              "discount_amount", "total", "lucky_roll_id", "converted_order_id",
              "created_at", "updated_at", "metadata"),
    "cart_by_session": ("session_id", "cart_id", "user_id", "status",
                        "updated_at"),
    "cart_by_user": ("user_id", "created_at", "cart_id", "status", "total",
                     "currency"),
    "cart_items": ("cart_id", "variant_id", "product_id", "product_name",
                   "variant_name", "attributes", "quantity", "unit_price",
                   "unit_discounted_price", "line_total", "currency", "added_at"),
    "orders": ("order_id", "user_id", "cart_id", "session_id", "anonymous_id",
               "source", "channel", "status", "currency", "item_count",
               "subtotal", "discount_pct", "discount_amount", "discount_reason",
               "tax_amount", "shipping_amount", "total_amount",
               "shipping_address", "created_at", "updated_at"),
    "orders_by_user": ("user_id", "created_at", "order_id", "status",
                       "total_amount", "currency", "item_count"),
    "order_items": ("order_id", "variant_id", "product_id", "product_name",
                    "variant_name", "attributes", "quantity", "unit_price",
                    "unit_discounted_price", "line_total", "currency"),
    "payments": ("payment_id", "order_id", "user_id", "attempt_no", "amount",
                 "currency", "method", "status", "gateway",
                 "gateway_transaction_ref", "gateway_fee", "failure_reason",
                 "created_at", "processed_at", "completed_at", "failed_at",
                 "refunded_at", "metadata"),
    "payments_by_order": ("order_id", "attempt_no", "payment_id", "status",
                          "amount", "currency", "method", "gateway", "created_at",
                          "completed_at", "failed_at"),
    "lucky_rolls": ("scope_type", "scope_id", "roll_date", "rolled_value", "won",
                    "discount_pct", "cart_id", "created_at"),
    "simulation_runs": ("run_id", "started_at", "finished_at", "status", "params",
                        "actuals", "row_counts"),
    "injected_issues": ("run_id", "issue_id", "table_name", "entity_id",
                        "column_name", "issue_type", "original_value",
                        "injected_value", "created_at"),
}


class Writer:
    """Buffers entity dicts and writes positional rows to Postgres."""

    def __init__(self, host: str, port: int, dbname: str, dry_run: bool = False,
                 max_inflight: int = 1024, user: str = "shop",
                 password: str = "shop"):
        self.host = host
        self.port = port
        self.dbname = dbname
        self.dry_run = dry_run
        # Kept for CLI compatibility; bounds per-table buffers instead.
        self.max_inflight = max(max_inflight, 1)
        self.user = user
        self.password = password
        self.conn = None
        self.counts: Counter = Counter()
        self._buffers: dict[str, list] = {}

    # -- lifecycle ---------------------------------------------------------
    def connect(self, reset: bool = False) -> None:
        if self.dry_run:
            return
        self.conn = psycopg.connect(
            host=self.host, port=self.port, dbname=self.dbname,
            user=self.user, password=self.password,
            connect_timeout=10, autocommit=True,
        )
        if reset:
            pg_schema.reset_schema(self.conn)
        else:
            pg_schema.create_schema(self.conn)

    def close(self) -> None:
        self.flush()
        if self.conn:
            self.conn.close()
            self.conn = None

    # -- writes ------------------------------------------------------------
    def _buffered(self, table: str, params: list) -> None:
        buf = self._buffers.setdefault(table, [])
        buf.append(pg_schema.adapt_row(params))
        if len(buf) >= BATCH_ROWS:
            self._flush_table(table)

    def _flush_table(self, table: str) -> None:
        buf = self._buffers.get(table)
        if not buf:
            return
        self._buffers[table] = []
        with self.conn.cursor() as cur:
            cur.executemany(pg_schema.insert_sql(table, ROW_ORDER[table]), buf)

    def flush(self) -> None:
        """Write every buffered row."""
        if self.dry_run:
            self._buffers.clear()
            return
        for table in list(self._buffers):
            self._flush_table(table)

    def write(self, table: str, entity: dict) -> None:
        self.counts[table] += 1
        if self.dry_run:
            return
        order = ROW_ORDER[table]
        self._buffered(table, [entity.get(col) for col in order])

    def write_many(self, table: str, entities: list[dict]) -> None:
        for entity in entities:
            self.write(table, entity)

    def write_positions(self, table: str, rows: list[tuple]) -> None:
        """Write rows already ordered to match ROW_ORDER[table]."""
        for row in rows:
            self.counts[table] += 1
            if self.dry_run:
                continue
            self._buffered(table, list(row))

    def as_row_counts(self) -> dict:
        return dict(self.counts)
