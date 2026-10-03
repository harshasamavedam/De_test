"""Unit tests for the shop simulator (no Cassandra required)."""

from __future__ import annotations

import random
from datetime import date, datetime
from decimal import Decimal

from shop.cart import CartFactory, compute_cart_totals
from shop.catalog import Catalog
from shop.config import LUCKY_WINNING_VALUES
from shop.dirty import IssueLedger
from shop.orders import build_order_items, compute_order_totals
from shop.simulator import SimParams, Simulator
from shop.writer import Writer


def _dry_run(seed=42, days=3, conversion="5", users="100-150"):
    params = SimParams(
        days=days,
        users_per_day=(int(users.split("-")[0]), int(users.split("-")[1])),
        conversion=Decimal(conversion),
        start_date=date(2026, 1, 1),
        seed=seed,
    )
    writer = Writer("127.0.0.1", 9042, "shop_test", dry_run=True)
    simulator = Simulator(params, writer)
    return simulator.run()


def test_conversion_is_close_to_target():
    summary = _dry_run(conversion="5")
    assert abs(summary["actual_conversion_pct"] - 5.0) <= 0.5


def test_simulation_is_deterministic():
    first = _dry_run(seed=7)
    second = _dry_run(seed=7)
    assert first["row_counts"] == second["row_counts"]
    assert first["sessions"] == second["sessions"]


def test_clean_profile_has_no_injected_issues():
    params = SimParams(
        days=2,
        users_per_day=(50, 80),
        conversion=Decimal("5"),
        start_date=date(2026, 1, 1),
        seed=1,
        dirty="clean",
    )
    writer = Writer("127.0.0.1", 9042, "shop_test", dry_run=True)
    summary = Simulator(params, writer).run()
    assert summary["injected_issues"] == 0


def test_zero_conversion_places_no_orders():
    summary = _dry_run(conversion="0")
    assert summary["orders"] == 0


def test_lucky_check_wins_on_winning_value():
    ledger = IssueLedger("run", 1, "clean")
    catalog = Catalog(1)
    factory = CartFactory(1, ledger, catalog)
    factory.rng = random.Random(0)

    # Force every roll to land on a winning number, then assert the prize.
    original_randint = factory.rng.randint

    def forced_randint(a, b):
        if (a, b) == (1, 1000):
            return LUCKY_WINNING_VALUES[0]
        return original_randint(a, b)

    factory.rng.randint = forced_randint
    result = factory.lucky_check(
        "user", "usr_1", "cart_1", date(2026, 1, 1), datetime(2026, 1, 1, 10)
    )
    assert result is not None
    assert result["won"] is True
    assert result["discount_pct"] == Decimal("20")


def test_lucky_check_only_once_per_day():
    ledger = IssueLedger("run", 1, "clean")
    catalog = Catalog(1)
    factory = CartFactory(1, ledger, catalog)
    day = date(2026, 1, 1)
    now = datetime(2026, 1, 1, 10)

    first = factory.lucky_check("user", "usr_1", "cart_1", day, now)
    second = factory.lucky_check("user", "usr_1", "cart_2", day, now)
    assert first is not None
    assert second is None  # already rolled today


def test_order_totals_apply_discount():
    items = [
        {
            "variant_id": "v1",
            "product_id": "p1",
            "product_name": "Widget",
            "variant_name": "Red",
            "attributes": {},
            "quantity": 2,
            "unit_price": Decimal("50.00"),
            "unit_discounted_price": Decimal("50.00"),
            "line_total": Decimal("100.00"),
            "currency": "USD",
        }
    ]
    items = build_order_items(items, "USD", "ord_1")
    totals = compute_order_totals(items, Decimal("20"))
    assert totals["subtotal"] == Decimal("100.00")
    assert totals["discount_amount"] == Decimal("20.00")
    assert totals["total_amount"] < totals["subtotal"]


def test_cart_totals_round_trip():
    items = [
        {"line_total": Decimal("30.00")},
        {"line_total": Decimal("20.00")},
    ]
    totals = compute_cart_totals(items, Decimal("10"))
    assert totals["subtotal"] == Decimal("50.00")
    assert totals["discount_amount"] == Decimal("5.00")
    assert totals["total"] == Decimal("45.00")
