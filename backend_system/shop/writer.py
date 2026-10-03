"""Cassandra writer for the shop simulator.

Wraps connection setup, keyspace reset, prepared statements and per-table
inserts. Supports a dry-run mode that only counts rows, so the generation logic
can be validated without a running Cassandra.
"""

from __future__ import annotations

from collections import Counter, deque

from cassandra.cluster import Cluster

from . import schema

# How many writes may be in flight before we start waiting on responses.
# Higher = more pipelining (faster) at the cost of memory; 1024 is a safe
# default for a single local node.
DEFAULT_MAX_INFLIGHT = 1024
# Cassandra client request timeout. The previous 10s default intermittently
# tripped on DDL (DROP/CREATE KEYSPACE) on a busy node.
DEFAULT_REQUEST_TIMEOUT = 30.0

# Column order for every prepared INSERT (must match shop/schema.INSERTS).
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
    "identity_map_by_user": ("user_id", "anonymous_id", "first_seen", "linked_at"),
    "events": ("session_id", "event_at", "event_id", "user_id", "anonymous_id",
               "event_type", "page", "product_id", "variant_id", "cart_id",
               "properties"),
    "categories": ("category_id", "name", "description", "product_count",
                   "created_at"),
    "products_by_category": ("category_id", "product_id", "product_name", "brand",
                             "variant_count", "created_at"),
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
    """Buffers entity dicts and writes positional rows to Cassandra."""

    def __init__(self, host: str, port: int, keyspace: str, dry_run: bool = False,
                 max_inflight: int = DEFAULT_MAX_INFLIGHT):
        self.host = host
        self.port = port
        self.keyspace = keyspace
        self.dry_run = dry_run
        self.max_inflight = max(max_inflight, 1)
        self.cluster = None
        self.session = None
        self.statements = {}
        self.counts: Counter = Counter()
        # Futures whose responses we have not waited on yet.
        self._inflight: deque = deque()

    # -- lifecycle ---------------------------------------------------------
    def connect(self, reset: bool = False) -> None:
        if self.dry_run:
            return
        self.cluster = Cluster([self.host], port=self.port)
        self.session = self.cluster.connect()
        self.session.default_timeout = DEFAULT_REQUEST_TIMEOUT
        if reset:
            schema.drop_keyspace(self.session, self.keyspace)
        schema.create_schema(self.session, self.keyspace)
        self.session.set_keyspace(self.keyspace)
        for table, cql in schema.INSERTS.items():
            self.statements[table] = self.session.prepare(cql)

    def close(self) -> None:
        self.flush()
        if self.cluster:
            self.cluster.shutdown()

    # -- writes ------------------------------------------------------------
    def _dispatch(self, table: str, params: list) -> None:
        """Send one write async, draining the oldest response when full."""
        future = self.session.execute_async(self.statements[table], params)
        self._inflight.append(future)
        if len(self._inflight) >= self.max_inflight:
            self._inflight.popleft().result()  # raises on write failure

    def flush(self) -> None:
        """Wait for every in-flight write to complete."""
        while self._inflight:
            self._inflight.popleft().result()

    def write(self, table: str, entity: dict) -> None:
        self.counts[table] += 1
        if self.dry_run:
            return
        order = ROW_ORDER[table]
        self._dispatch(table, [entity.get(col) for col in order])

    def write_many(self, table: str, entities: list[dict]) -> None:
        for entity in entities:
            self.write(table, entity)

    def write_positions(self, table: str, rows: list[tuple]) -> None:
        """Write rows already ordered to match ROW_ORDER[table]."""
        for row in rows:
            self.counts[table] += 1
            if self.dry_run:
                continue
            self._dispatch(table, list(row))

    def as_row_counts(self) -> dict:
        return dict(self.counts)
