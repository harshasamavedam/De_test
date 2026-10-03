"""Deterministic id helpers for the shop simulator.

Ids are human-readable and encode the type plus a sortable component so
generated data is easy to inspect and reason about.
"""

from __future__ import annotations

from datetime import date


def user_id(n: int) -> str:
    return f"usr_{n:07d}"


def anonymous_id(n: int) -> str:
    return f"anon_{n:09d}"


def session_id(day: date, n: int) -> str:
    return f"sess_{day:%Y%m%d}_{n:07d}"


def event_id(session: str, n: int) -> str:
    return f"evt_{session}_{n:04d}"


def category_id(slug: str) -> str:
    return slug


def product_id(slug: str, n: int) -> str:
    return f"prd_{slug[:3]}_{n:04d}"


def variant_id(product: str, n: int) -> str:
    return f"{product}_v{n}"


def cart_id(day: date, n: int) -> str:
    return f"cart_{day:%Y%m%d}_{n:07d}"


def order_id(day: date, n: int) -> str:
    return f"ord_{day:%Y%m%d}_{n:07d}"


def payment_id(day: date, n: int) -> str:
    return f"pay_{day:%Y%m%d}_{n:07d}"


def address_id(n: int) -> str:
    return f"addr_{n:07d}"


def sku(product: str, n: int) -> str:
    return f"{product[-6:].upper()}-{n:02d}"


def run_id(seed: int, start: date, days: int) -> str:
    return f"run_{start:%Y%m%d}_{days}d_seed{seed}"
