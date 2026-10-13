"""Tests for the read-only query guard and the exploration UI endpoints."""

from __future__ import annotations

import pytest

from shop import query


@pytest.mark.parametrize("sql", [
    "SELECT * FROM orders",
    "select order_id from orders limit 5",
    "  SELECT * FROM carts  ;  ",
    "SELECT o.order_id, i.quantity FROM orders o JOIN order_items i ON i.order_id = o.order_id LIMIT 5",
])
def test_validate_accepts_select(sql):
    assert query.validate(sql)


@pytest.mark.parametrize("sql", [
    "",
    "   ",
    "DROP TABLE orders",
    "INSERT INTO orders (order_id) VALUES ('x')",
    "UPDATE carts SET status = 'x' WHERE cart_id = 'y'",
    "DELETE FROM orders WHERE order_id = 'x'",
    "SELECT * FROM orders; SELECT * FROM carts",
    "SELECT * FROM orders DROP",
])
def test_validate_rejects_bad_queries(sql):
    with pytest.raises(query.QueryError):
        query.validate(sql)


def test_presets_present():
    labels = {p["label"] for p in query.PRESETS}
    assert {"Orders", "Payments", "Categories", "Injected issues"} <= labels
    for preset in query.PRESETS:
        assert query.validate(preset["sql"])
