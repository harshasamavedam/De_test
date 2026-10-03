"""Cart, cart-item and Lucky Check generation.

Carts belong to a session (and optionally a stitched user). Only logged-in
users convert a cart to an order. The Lucky Check rolls once per user (or per
anonymous visitor) per day.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from . import config, ids

# Lucky-roll id counter is process-wide via the factory instance.
CART_STATUS_ACTIVE = "active"
CART_STATUS_CONVERTED = "converted"
CART_STATUS_ABANDONED = "abandoned"


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CartFactory:
    def __init__(self, seed: int, ledger, catalog):
        self.seed = seed
        self.ledger = ledger
        self.catalog = catalog
        self.rng = random.Random(f"cart:{seed}")
        self.counter = 0
        # (scope_type, scope_id, date) -> roll dict, to enforce once-per-day.
        self.rolls: dict[tuple, dict] = {}

    def next_cart_id(self, day: date) -> str:
        self.counter += 1
        return ids.cart_id(day, self.counter)

    def build_items(self, currency_rate: Decimal, currency: str) -> list[dict]:
        rng = self.rng
        variants = self.catalog.active_variants()
        n_items = 1
        if rng.random() < config.MULTI_ITEM_CART_RATE:
            n_items = rng.randint(2, config.MAX_CART_ITEMS)
        chosen = rng.sample(variants, min(n_items, len(variants)))

        items = []
        for v in chosen:
            qty = rng.randint(1, config.MAX_LINE_QUANTITY)
            unit_price = _money(v["price_usd"] * currency_rate)
            unit_discounted = _money(v["discounted_price_usd"] * currency_rate)
            line_total = _money(unit_discounted * qty)

            # Financial quality issue: discounted price above list price.
            if self.ledger.chance("financial_discounted_above") and unit_discounted <= unit_price:
                broken = _money(unit_price * Decimal("1.15"))
                self.ledger.record(
                    "cart_items", v["variant_id"], "unit_discounted_price",
                    "financial_discounted_above", unit_discounted, broken,
                )
                unit_discounted = broken
                line_total = _money(unit_discounted * qty)

            # Financial quality issue: negative quantity.
            if self.ledger.chance("financial_negative_qty"):
                self.ledger.record(
                    "cart_items", v["variant_id"], "quantity",
                    "financial_negative_qty", qty, -qty,
                )
                qty = -qty

            items.append(
                {
                    "variant_id": v["variant_id"],
                    "product_id": v["product_id"],
                    "product_name": v["product_name"],
                    "variant_name": v["variant_name"],
                    "attributes": v["attributes"],
                    "quantity": qty,
                    "unit_price": unit_price,
                    "unit_discounted_price": unit_discounted,
                    "line_total": line_total,
                }
            )
        return items

    def lucky_check(
        self,
        scope_type: str,
        scope_id: str,
        cart_id: str,
        roll_date: date,
        now: datetime,
    ) -> dict | None:
        """Return a roll result if allowed today, else None if already rolled."""
        key = (scope_type, scope_id, roll_date)
        if key in self.rolls:
            return None  # once per day
        rolled = self.rng.randint(config.LUCKY_ROLL_MIN, config.LUCKY_ROLL_MAX)
        won = rolled in config.LUCKY_WINNING_VALUES
        result = {
            "roll_id": f"roll_{scope_type}_{scope_id}_{roll_date:%Y%m%d}",
            "scope_type": scope_type,
            "scope_id": scope_id,
            "roll_date": roll_date,
            "rolled_value": rolled,
            "won": won,
            "discount_pct": config.LUCKY_DISCOUNT_PCT if won else Decimal("0"),
            "cart_id": cart_id,
            "created_at": now,
        }
        self.rolls[key] = result
        return result


def compute_cart_totals(items: list[dict], discount_pct: Decimal) -> dict:
    subtotal = _money(sum((i["line_total"] for i in items), Decimal("0")))
    # Financial quality issue: rounding drift in totals.
    discount_amount = _money(subtotal * discount_pct / Decimal("100"))
    total = _money(subtotal - discount_amount)
    return {
        "item_count": len(items),
        "subtotal": subtotal,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "total": total,
    }
