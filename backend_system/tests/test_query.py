"""Tests for the read-only query guard and the exploration UI endpoints."""

from __future__ import annotations

import pytest

from shop import query


@pytest.mark.parametrize("cql", [
    "SELECT * FROM orders",
    "select order_id from orders limit 5",
    "  SELECT * FROM carts  ;  ",
])
def test_validate_accepts_select(cql):
    assert query.validate(cql)


@pytest.mark.parametrize("cql", [
    "",
    "   ",
    "DROP TABLE orders",
    "INSERT INTO orders (order_id) VALUES ('x')",
    "UPDATE carts SET status = 'x' WHERE cart_id = 'y'",
    "DELETE FROM orders WHERE order_id = 'x'",
    "SELECT * FROM orders; SELECT * FROM carts",
    "SELECT * FROM orders ALLOW FILTERING DROP",
])
def test_validate_rejects_bad_queries(cql):
    with pytest.raises(query.QueryError):
        query.validate(cql)


def test_presets_present():
    labels = {p["label"] for p in query.PRESETS}
    assert {"Orders", "Payments", "Categories", "Injected issues"} <= labels
    for preset in query.PRESETS:
        assert query.validate(preset["cql"])
