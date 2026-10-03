"""Seed synthetic customers, pending orders, and linked product variants."""

import argparse
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from cassandra.cluster import Cluster

from cassandra_setup import initialize_cassandra_schema


CUSTOMER_INSERT = """
INSERT INTO customers_table (
    customer_id, first_name, last_name, email, phone, date_of_birth,
    address_line, city, region, postal_code, country, latitude, longitude,
    metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

ORDER_INSERT = """
INSERT INTO orders_table (
    order_id, customer_id, amount, currency, status, created_at, updated_at,
    payment_method, payment_id, metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

ORDER_ITEM_INSERT = """
INSERT INTO customer_order_items_by_customer (
    customer_id, created_at, order_id, product_id, variant_id, category,
    brand, product_name, variant_name, quantity, unit_price, order_status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

FIRST_NAMES = ("Avery", "Jordan", "Morgan", "Riley", "Casey", "Taylor", "Quinn", "Cameron")
LAST_NAMES = ("Parker", "Reed", "Hayes", "Brooks", "Bennett", "Foster", "Rivera", "Bailey")
STREET_NAMES = ("Maple", "Cedar", "Pine", "Lake", "Hill", "Oak", "Willow", "Park")
LOCATIONS = (
    ("Seattle", "WA", "98101", 47.6062, -122.3321),
    ("Austin", "TX", "78701", 30.2672, -97.7431),
    ("Denver", "CO", "80202", 39.7392, -104.9903),
    ("Boston", "MA", "02108", 42.3601, -71.0589),
    ("Portland", "OR", "97201", 45.5152, -122.6784),
    ("Chicago", "IL", "60601", 41.8781, -87.6298),
)
CATEGORIES = ("electronics", "clothing", "other")


def build_customer(customer_number: int, randomizer: random.Random):
    customer_id = f"CUST-DEMO-{customer_number:04d}"
    first_name = randomizer.choice(FIRST_NAMES)
    last_name = randomizer.choice(LAST_NAMES)
    city, region, postal_code, latitude, longitude = randomizer.choice(LOCATIONS)
    birth_year = randomizer.randint(1960, 2002)
    birth_date = date(birth_year, randomizer.randint(1, 12), randomizer.randint(1, 28))
    street_number = randomizer.randint(100, 9999)
    street_name = randomizer.choice(STREET_NAMES)

    values = (
        customer_id,
        first_name,
        last_name,
        f"customer{customer_number:04d}@example.com",
        f"+1-202-555-{1000 + customer_number:04d}",
        birth_date,
        f"{street_number} {street_name} St (synthetic)",
        city,
        region,
        postal_code,
        "US",
        latitude,
        longitude,
        {"source": "synthetic", "pii": "fictional"},
    )
    return customer_id, values


def populate(host: str, port: int, keyspace: str, customer_count: int, seed: int):
    initialize_cassandra_schema([host], port=port, keyspace=keyspace)
    randomizer = random.Random(seed)
    cluster = Cluster([host], port=port)
    session = cluster.connect(keyspace)
    customers = session.prepare(CUSTOMER_INSERT)
    orders = session.prepare(ORDER_INSERT)
    order_items = session.prepare(ORDER_ITEM_INSERT)

    try:
        catalog = []
        for category in CATEGORIES:
            catalog.extend(
                session.execute(
                    "SELECT category, brand, product_id, product_name, "
                    "variant_id, variant_name, price, is_active "
                    "FROM product_item WHERE category = %s",
                    (category,),
                )
            )
        catalog = [item for item in catalog if item.is_active]
        if not catalog:
            raise RuntimeError("No active catalog variants found; seed product_item first.")

        sample_customer_ids = []
        total_items = 0
        anchor = datetime(2026, 10, 3)

        for customer_number in range(1, customer_count + 1):
            customer_id, customer_values = build_customer(customer_number, randomizer)
            session.execute(customers, customer_values)

            order_id = f"ORD-DEMO-{customer_number:04d}"
            created_at = anchor - timedelta(
                days=randomizer.randrange(730), seconds=randomizer.randrange(86400)
            )
            selected_items = randomizer.sample(catalog, randomizer.randint(2, 4))
            line_data = []
            order_total = Decimal("0.00")

            for catalog_item in selected_items:
                quantity = randomizer.randint(1, 3)
                unit_price = catalog_item.price
                order_total += unit_price * quantity
                line_data.append((catalog_item, quantity, unit_price))

            session.execute(
                orders,
                (
                    order_id,
                    customer_id,
                    order_total,
                    "USD",
                    "pending",
                    created_at,
                    None,
                    None,
                    None,
                    {"source": "synthetic", "dataset": "customer-product-demo"},
                ),
            )

            for catalog_item, quantity, unit_price in line_data:
                session.execute(
                    order_items,
                    (
                        customer_id,
                        created_at,
                        order_id,
                        catalog_item.product_id,
                        catalog_item.variant_id,
                        catalog_item.category,
                        catalog_item.brand,
                        catalog_item.product_name,
                        catalog_item.variant_name,
                        quantity,
                        unit_price,
                        "pending",
                    ),
                )
                total_items += 1

            if customer_number in {1, customer_count}:
                sample_customer_ids.append((customer_id, order_id))

        for customer_id, order_id in sample_customer_ids:
            customer = session.execute(
                "SELECT customer_id FROM customers_table WHERE customer_id = %s",
                (customer_id,),
            ).one()
            linked_rows = list(
                session.execute(
                    "SELECT order_id, product_id, variant_id "
                    "FROM customer_order_items_by_customer WHERE customer_id = %s",
                    (customer_id,),
                )
            )
            if not customer or not linked_rows or any(row.order_id != order_id for row in linked_rows):
                raise RuntimeError(f"Customer/order/product link verification failed for {customer_id}")

        return total_items
    finally:
        cluster.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=300, help="Number of demo customers")
    parser.add_argument("--seed", type=int, default=20261003)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9042)
    parser.add_argument("--keyspace", default="payments")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")

    total_items = populate(args.host, args.port, args.keyspace, args.count, args.seed)
    print(
        f"Verified {args.count:,} synthetic customers, {args.count:,} linked orders, "
        f"and {total_items:,} order-item variant rows."
    )


if __name__ == "__main__":
    main()