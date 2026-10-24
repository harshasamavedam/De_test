"""Read-only SQL query runner for the exploration UI.

Postgres speaks real SQL (joins and all), so this is a small guarded runner
rather than a general database console. Only single SELECT statements are
allowed, row counts are capped, and each query gets a 10s statement timeout
(set on the repository connection).
"""

from __future__ import annotations

import re

from .repository import ShopRepository

# Leading keyword must be SELECT or WITH (CTEs are fine in Postgres).
_START_OK = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# Any of these anywhere in the statement makes it non read-only.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|grant|revoke|"
    r"copy|call|do|listen|notify|vacuum|analyse|analyze|explain)\b",
    re.IGNORECASE,
)

MAX_ROWS = 200


class QueryError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate(sql: str) -> str:
    text = (sql or "").strip().rstrip(";").strip()
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


def run(repository: ShopRepository, sql: str) -> dict:
    text = validate(sql)
    try:
        with repository.conn.cursor() as cur:
            cur.execute(text)
            if cur.description is None:
                columns: list = []
                rows: list = []
            else:
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchmany(MAX_ROWS + 1)
    except QueryError:
        raise
    except Exception as exc:  # syntax errors, unknown tables, timeout, etc.
        raise QueryError(f"query failed: {exc}") from exc

    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    return {
        "columns": columns,
        "rows": [{c: _stringify(row[c]) for c in columns} for row in rows],
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
    {"label": "Tables", "sql": "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"},
    {"label": "Categories", "sql": "SELECT * FROM categories"},
    {"label": "Products", "sql": "SELECT * FROM products_by_category LIMIT 25"},
    {"label": "Variants", "sql": "SELECT * FROM variants_by_product LIMIT 25"},
    {"label": "Recent sessions", "sql": "SELECT session_id, channel, source, device, started_at FROM sessions LIMIT 25"},
    {"label": "Carts", "sql": "SELECT cart_id, status, item_count, subtotal, discount_pct, total FROM carts LIMIT 25"},
    {"label": "Cart items", "sql": "SELECT cart_id, variant_id, quantity, unit_discounted_price, line_total FROM cart_items LIMIT 25"},
    {"label": "Orders", "sql": "SELECT order_id, user_id, status, currency, item_count, total_amount, discount_reason FROM orders LIMIT 25"},
    {"label": "Order items", "sql": "SELECT order_id, variant_id, product_name, quantity, line_total FROM order_items LIMIT 25"},
    {"label": "Payments", "sql": "SELECT payment_id, order_id, attempt_no, status, method, amount FROM payments LIMIT 25"},
    {"label": "Lucky rolls", "sql": "SELECT scope_type, scope_id, roll_date, rolled_value, won, discount_pct FROM lucky_rolls LIMIT 25"},
    {"label": "Identity map", "sql": "SELECT anonymous_id, user_id, link_source FROM identity_map LIMIT 25"},
    {"label": "Injected issues", "sql": "SELECT table_name, column_name, issue_type, injected_value FROM injected_issues LIMIT 25"},
    {"label": "Simulation runs", "sql": "SELECT run_id, status, params, actuals FROM simulation_runs LIMIT 10"},
]
