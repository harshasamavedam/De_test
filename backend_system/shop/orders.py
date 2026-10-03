"""Order and order-item generation.

Orders snapshot item prices at purchase time and snapshot the traffic source
from the originating session for attribution. The frozen Lucky Check discount
carries over from the cart.
"""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from . import config

ORDER_STATUS_COMPLETED = "completed"
ORDER_STATUS_PENDING = "pending"
ORDER_STATUS_PROCESSING = "processing"
ORDER_STATUS_CANCELLED = "cancelled"
ORDER_STATUS_REFUNDED = "refunded"


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_order_items(cart_items: list[dict], currency: str, order_id: str) -> list[dict]:
    """Freeze cart items into order items (price snapshot)."""
    items = []
    for ci in cart_items:
        items.append(
            {
                "order_id": order_id,
                "variant_id": ci["variant_id"],
                "product_id": ci["product_id"],
                "product_name": ci["product_name"],
                "variant_name": ci["variant_name"],
                "attributes": ci["attributes"],
                "quantity": ci["quantity"],
                "unit_price": ci["unit_price"],
                "unit_discounted_price": ci["unit_discounted_price"],
                "line_total": ci["line_total"],
                "currency": currency,
            }
        )
    return items


def compute_order_totals(items: list[dict], discount_pct: Decimal, ledger=None,
                         order_id: str = "") -> dict:
    subtotal = _money(sum((i["line_total"] for i in items), Decimal("0")))
    discount_amount = _money(subtotal * discount_pct / Decimal("100"))

    # Financial quality issue: rounding drift on the order total.
    drift = Decimal("0")
    if ledger is not None and ledger.chance("financial_rounding"):
        drift = Decimal(random.choice(("0.01", "-0.01", "0.02")))
        ledger.record(
            "orders", order_id, "total_amount", "financial_rounding", None, drift
        )

    taxable = subtotal - discount_amount
    tax_amount = _money(taxable * config.TAX_RATE)
    shipping_amount = (
        Decimal("0.00")
        if taxable >= config.FREE_SHIPPING_THRESHOLD
        else config.SHIPPING_FLAT
    )
    total_amount = _money(taxable + tax_amount + shipping_amount + drift)
    return {
        "item_count": len(items),
        "subtotal": subtotal,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "tax_amount": tax_amount,
        "shipping_amount": shipping_amount,
        "total_amount": total_amount,
    }


def shipping_address_snapshot(user: dict, address: tuple | None) -> dict:
    if address is None:
        return {
            "full_name": f"{user['first_name']} {user['last_name']}",
            "city": "", "region": "", "postal_code": "", "country": user["country"] or "",
        }
    _uid, _aid, _label, full_name, line1, _line2, city, region, postal, country, _phone, _def, _created = address
    return {
        "full_name": full_name,
        "line1": line1,
        "city": city,
        "region": region,
        "postal_code": postal,
        "country": country,
    }
