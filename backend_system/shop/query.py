"""Read-only CQL query runner for the exploration UI.

Cassandra speaks CQL, not SQL, so this is a small guarded runner rather than a
general database console. Only single SELECT statements against the shop
keyspace are allowed, row counts are capped, and each query gets a timeout.
"""

from __future__ import annotations

import re

from .repository import ShopRepository

# Leading keyword must be SELECT (WITH ... SELECT is not supported by Cassandra
# the way SQL CTEs are, so plain SELECT is enough).
_START_OK = re.compile(r"^\s*(select)\b", re.IGNORECASE)

# Any of these anywhere in the statement makes it non read-only.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|grant|revoke|"
    r"batch|apply|use|copy|begin|list|alter)\b",
    re.IGNORECASE,
)

MAX_ROWS = 200


class QueryError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate(cql: str) -> str:
    text = (cql or "").strip().rstrip(";").strip()
    if not text:
        raise QueryError("query is empty")
    if ";" in text:
        raise QueryError("only a single statement is allowed")
    if not _START_OK.match(text):
        raise QueryError("only SELECT statements are allowed")
    # strip the leading keyword before scanning for forbidden words so the word
    # 'select' itself is fine, then scan the rest.
    rest = _START_OK.sub("", text, count=1)
    match = _FORBIDDEN.search(rest)
    if match:
        raise QueryError(f"keyword '{match.group(1)}' is not allowed (read-only)")
    return text


def run(repository: ShopRepository, cql: str) -> dict:
    text = validate(cql)
    session = repository.session
    try:
        statement = session.prepare(text)
    except Exception as exc:  # syntax errors, unknown tables, etc.
        raise QueryError(f"CQL error: {exc}") from exc

    try:
        rows = list(session.execute(statement, timeout=10))
    except Exception as exc:
        raise QueryError(f"query failed: {exc}") from exc

    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    if rows:
        columns = list(rows[0].keys())
    else:
        metadata = getattr(statement, "column_metadata", None) or []
        columns = [entry[0] for entry in metadata]
    return {
        "columns": columns,
        "rows": [{c: _stringify(row.get(c)) for c in columns} for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
    }


def _stringify(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


# Preset queries shown as buttons in the UI, grouped for orientation.
PRESETS = [
    {"label": "Tables", "cql": "SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'shop'"},
    {"label": "Categories", "cql": "SELECT * FROM categories"},
    {"label": "Products", "cql": "SELECT * FROM products_by_category LIMIT 25"},
    {"label": "Variants", "cql": "SELECT * FROM variants_by_product LIMIT 25"},
    {"label": "Recent sessions", "cql": "SELECT session_id, channel, source, device, started_at FROM sessions LIMIT 25"},
    {"label": "Carts", "cql": "SELECT cart_id, status, item_count, subtotal, discount_pct, total FROM carts LIMIT 25"},
    {"label": "Cart items", "cql": "SELECT cart_id, variant_id, quantity, unit_discounted_price, line_total FROM cart_items LIMIT 25"},
    {"label": "Orders", "cql": "SELECT order_id, user_id, status, currency, item_count, total_amount, discount_reason FROM orders LIMIT 25"},
    {"label": "Order items", "cql": "SELECT order_id, variant_id, product_name, quantity, line_total FROM order_items LIMIT 25"},
    {"label": "Payments", "cql": "SELECT payment_id, order_id, attempt_no, status, method, amount FROM payments LIMIT 25"},
    {"label": "Lucky rolls", "cql": "SELECT scope_type, scope_id, roll_date, rolled_value, won, discount_pct FROM lucky_rolls LIMIT 25"},
    {"label": "Identity map", "cql": "SELECT anonymous_id, user_id, link_source FROM identity_map LIMIT 25"},
    {"label": "Injected issues", "cql": "SELECT table_name, column_name, issue_type, injected_value FROM injected_issues LIMIT 25"},
    {"label": "Simulation runs", "cql": "SELECT run_id, status, params, actuals FROM simulation_runs LIMIT 10"},
]
