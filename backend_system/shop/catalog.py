"""Catalog generation: categories, products and variants.

The catalog is small and deterministic (7-8 categories, a handful of products
per brand, a few variants each). Prices are generated in USD then converted to
a display currency, and a `discounted_price` (catalog sale price) is derived.
"""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from . import config, ids


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Catalog:
    """In-memory catalog with lookup helpers used across the simulator."""

    def __init__(self, seed: int):
        self.seed = seed
        self.categories: list[dict] = []
        self.products: list[dict] = []
        self.variants: list[dict] = []
        self._variants_by_id: dict[str, dict] = {}
        self._build()

    def _build(self) -> None:
        rng = random.Random(f"catalog:{self.seed}")
        now = datetime.utcnow()

        for slug, spec in config.CATEGORIES.items():
            cat_id = ids.category_id(slug)
            products_here = []
            for brand_index, brand in enumerate(spec["brands"]):
                for p in range(config.PRODUCTS_PER_BRAND):
                    base = spec["products"][(p + brand_index) % len(spec["products"])]
                    product_id = ids.product_id(slug, len(self.products) + 1)
                    product = {
                        "product_id": product_id,
                        "category_id": cat_id,
                        "product_name": base,
                        "brand": brand,
                    }
                    self.products.append(product)
                    products_here.append(product)

                    attributes = config.VARIANT_ATTRIBUTES[slug]
                    for v in range(1, config.VARIANTS_PER_PRODUCT + 1):
                        variant = self._make_variant(
                            rng, product, base, brand, slug, v, attributes
                        )
                        self.variants.append(variant)
                        self._variants_by_id[variant["variant_id"]] = variant

            self.categories.append(
                {
                    "category_id": cat_id,
                    "name": spec["name"],
                    "description": f"Synthetic catalog for {spec['name']}",
                    "product_count": len(products_here),
                    "created_at": now,
                }
            )

    def _make_variant(
        self,
        rng: random.Random,
        product: dict,
        base: str,
        brand: str,
        slug: str,
        index: int,
        attributes_spec,
    ) -> dict:
        variant_id = ids.variant_id(product["product_id"], index)
        low, high = config.PRICE_BANDS_USD[slug]
        price_usd = _money(Decimal(rng.uniform(low, high)))
        # Catalog sale price: either no discount or 5-35% off.
        if rng.random() < 0.45:
            discount = Decimal(rng.uniform(0.05, 0.35))
            discounted = _money(price_usd * (Decimal("1") - discount))
        else:
            discounted = price_usd

        attrs = {}
        for attr_name, choices in attributes_spec:
            attrs[attr_name] = rng.choice(choices)

        variant_name = " / ".join(attrs.values()) or "Standard"
        return {
            "variant_id": variant_id,
            "product_id": product["product_id"],
            "category_id": product["category_id"],
            "product_name": base,
            "variant_name": variant_name,
            "sku": ids.sku(product["product_id"], index),
            "attributes": attrs,
            "price_usd": price_usd,
            "discounted_price_usd": discounted,
            "is_active": True,
            "brand": brand,
        }

    # -- lookups -----------------------------------------------------------
    def variant(self, variant_id: str) -> dict | None:
        return self._variants_by_id.get(variant_id)

    def active_variants(self) -> list[dict]:
        return self.variants

    def variant_count_by_product(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.variants:
            counts[v["product_id"]] = counts.get(v["product_id"], 0) + 1
        return counts
