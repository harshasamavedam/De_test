"""Generate synthetic orders and linked payments in local Cassandra."""

import argparse
import random
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from cassandra.cluster import Cluster

from cassandra_setup import initialize_cassandra_schema


ORDER_INSERT = """
INSERT INTO orders_table (
    order_id, customer_id, amount, currency, status, created_at,
    updated_at, payment_method, payment_id, metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

PAYMENT_INSERT = """
INSERT INTO payments_table (
    payment_id, order_id, customer_id, amount, currency, payment_method,
    status, created_at, processed_at, completed_at, failed_at, refunded_at,
    gateway_response, gateway_fee, transaction_reference, metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

CUSTOMER_INSERT = """
INSERT INTO customers_table (
    customer_id, first_name, last_name, email, phone, date_of_birth,
    address_line, city, region, postal_code, country, latitude, longitude,
    metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

PRODUCT_ITEM_INSERT = """
INSERT INTO product_item (
    category, brand, product_id, product_name, variant_id, variant_name,
    sku, color, size, price, cost, stock, warehouse, is_active, metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

PAYMENT_METHODS = ("credit_card", "paypal", "bank_transfer")
FIRST_NAMES = ("Avery", "Jordan", "Morgan", "Riley", "Casey", "Taylor", "Quinn", "Cameron")
LAST_NAMES = ("Parker", "Reed", "Hayes", "Brooks", "Morgan", "Bennett", "Foster", "Rivera")
CATEGORY_BRANDS = {
    "electronics": ("Apex", "Nexa", "VoltEdge", "Orbit"),
    "clothing": ("Northline", "Harbor", "Summit", "Luma"),
    "other": ("Terra", "Hearth", "Cascade", "Meridian"),
}
PRODUCT_NAMES = {
    "electronics": (
        "Smart Speaker",
        "Wireless Earbuds",
        "4K Monitor",
        "Laptop Stand",
        "Bluetooth Tracker",
        "Gaming Pad",
        "USB Dock",
        "Portable Charger",
    ),
    "clothing": (
        "Performance Tee",
        "Classic Hoodie",
        "Trail Jacket",
        "Everyday Pants",
        "Athletic Shorts",
        "Travel Backpack",
        "Fleece Pullover",
        "Canvas Cap",
    ),
    "other": (
        "Desk Organizer",
        "Cookware Set",
        "Yoga Mat",
        "Bottle Set",
        "Pet Feeder",
        "Home Lamp",
        "Storage Bin",
        "Travel Mug",
    ),
}
VARIANT_NAMES = ("Standard", "Deluxe", "Pro", "Studio")
COLORS = ("Black", "White", "Blue", "Red", "Gray", "Silver")
SIZES = ("S", "M", "L", "XL", "One Size")
WAREHOUSES = ("SEA", "AUS", "DEN", "BOS", "CHI")
LOCATIONS = (
    ("Seattle", "WA", "98101", 47.6062, -122.3321),
    ("Austin", "TX", "78701", 30.2672, -97.7431),
    ("Denver", "CO", "80202", 39.7392, -104.9903),
    ("Boston", "MA", "02108", 42.3601, -71.0589),
    ("Portland", "OR", "97201", 45.5152, -122.6784),
    ("Chicago", "IL", "60601", 41.8781, -87.6298),
)
STREET_NAMES = ("Maple", "Cedar", "Pine", "Lake", "Hill", "Oak", "Willow", "Park")
STATUS_WEIGHTS = (68, 12, 8, 5, 3, 4)
STATUS_PAIRS = (
    ("completed", "completed"),
    ("pending", "pending"),
    ("processing", "processing"),
    ("cancelled", "cancelled"),
    ("refunded", "refunded"),
    ("processing", "failed"),
)


def generated_customer(customer_id: str, seed: int):
    """Build repeatable, clearly synthetic customer PII and fictional address data."""
    customer_number = int(customer_id.removeprefix("CUST-"))
    randomizer = random.Random(f"{seed}:{customer_id}")
    first_name = FIRST_NAMES[(customer_number + seed) % len(FIRST_NAMES)]
    last_name = LAST_NAMES[(customer_number // len(FIRST_NAMES) + seed) % len(LAST_NAMES)]
    city, region, postal_code, latitude, longitude = randomizer.choice(LOCATIONS)

    return (
        customer_id,
        first_name,
        last_name,
        f"{first_name.lower()}.{last_name.lower()}.{customer_number}@example.com",
        f"+1-202-555-{1000 + customer_number % 9000:04d}",
        date(1960 + customer_number % 40, 1 + customer_number % 12, 1 + customer_number % 28),
        f"{100 + customer_number % 9900} {randomizer.choice(STREET_NAMES)} St (synthetic)",
        city,
        region,
        postal_code,
        "US",
        latitude,
        longitude,
        {"source": "synthetic", "seed": str(seed), "pii": "fictional"},
    )


def generated_product_catalog(seed: int):
    """Yield synthetic product/variant rows for the catalog tables."""
    randomizer = random.Random(seed)
    for category, brands in CATEGORY_BRANDS.items():
        for brand_index, brand in enumerate(brands):
            for product_index in range(1, 5):
                product_name = PRODUCT_NAMES[category][(product_index + brand_index) % len(PRODUCT_NAMES[category])]
                product_id = f"{category[:3].upper()}-{brand[:3].upper()}-{product_index:02d}"
                for variant_index in range(1, 5):
                    variant_name = VARIANT_NAMES[(variant_index + product_index + brand_index) % len(VARIANT_NAMES)]
                    variant_id = f"{product_id}-V{variant_index}"
                    sku = f"{brand[:3].upper()}{category[:2].upper()}{product_index:02d}{variant_index:02d}"
                    price = Decimal(randomizer.randint(1800, 180000)) / 100
                    cost = (price * Decimal("0.68")).quantize(Decimal("0.01"))
                    stock = randomizer.randint(15, 250)
                    warehouse = randomizer.choice(WAREHOUSES)
                    color = randomizer.choice(COLORS)
                    size = randomizer.choice(SIZES) if category == "clothing" else randomizer.choice(("Small", "Medium", "Large", "Standard"))
                    metadata = {
                        "source": "synthetic",
                        "seed": str(seed),
                        "brand": brand,
                        "variant": variant_name,
                    }
                    yield (
                        category,
                        brand,
                        product_id,
                        product_name,
                        variant_id,
                        variant_name,
                        sku,
                        color,
                        size,
                        price,
                        cost,
                        stock,
                        warehouse,
                        True,
                        metadata,
                    )


def insert_product_catalog(host: str, port: int, keyspace: str, seed: int) -> dict:
    """Insert and verify the deterministic product catalog without generating orders."""
    initialize_cassandra_schema([host], port=port, keyspace=keyspace)
    product_rows = list(generated_product_catalog(seed))
    cluster = Cluster([host], port=port)
    session = cluster.connect(keyspace)

    try:
        product_statement = session.prepare(PRODUCT_ITEM_INSERT)
        for product_row in product_rows:
            session.execute(product_statement, product_row)

        counts = {}
        for category in CATEGORY_BRANDS:
            expected = {
                (row[2], row[4]) for row in product_rows if row[0] == category
            }
            stored = session.execute(
                "SELECT product_id, variant_id FROM product_item WHERE category = %s",
                (category,),
            )
            actual = {(row.product_id, row.variant_id) for row in stored}
            if actual != expected:
                raise RuntimeError(
                    f"Catalog verification failed for {category}: "
                    f"expected {len(expected)} variants, found {len(actual)}"
                )
            counts[category] = len(actual)
    finally:
        cluster.shutdown()

    return counts


def generated_rows(days: int, orders_per_day: int, seed: int, end_date: date):
    """Yield paired order/payment values over a reproducible date range."""
    randomizer = random.Random(seed)
    first_day = end_date - timedelta(days=days - 1)

    for day_offset in range(days):
        order_day = first_day + timedelta(days=day_offset)
        for sequence in range(orders_per_day):
            order_id = f"ORD-SYN-{order_day:%Y%m%d}-{sequence:04d}"
            payment_id = f"PAY-SYN-{order_day:%Y%m%d}-{sequence:04d}"
            customer_id = f"CUST-{randomizer.randint(1, 5000):05d}"
            payment_method = randomizer.choice(PAYMENT_METHODS)
            order_status, payment_status = randomizer.choices(
                STATUS_PAIRS, weights=STATUS_WEIGHTS, k=1
            )[0]

            if randomizer.random() < 0.005:
                amount = Decimal("0.00")
            elif randomizer.random() < 0.015:
                amount = Decimal(randomizer.randint(100000, 500000)) / 100
            else:
                amount = Decimal(randomizer.randint(500, 25000)) / 100

            created_at = datetime.combine(
                order_day,
                time(
                    randomizer.randrange(24),
                    randomizer.randrange(60),
                    randomizer.randrange(60),
                ),
            )
            processed_at = created_at + timedelta(seconds=randomizer.randint(1, 90))
            completed_at = processed_at + timedelta(seconds=randomizer.randint(1, 120))
            payment_created_at = created_at
            payment_processed_at = processed_at if payment_status != "pending" else None
            payment_completed_at = (
                completed_at if payment_status in {"completed", "refunded"} else None
            )
            failed_at = processed_at if payment_status == "failed" else None
            refunded_at = completed_at if payment_status == "refunded" else None
            updated_at = completed_at if order_status in {"completed", "refunded"} else None

            order_values = (
                order_id,
                customer_id,
                amount,
                "USD",
                order_status,
                created_at,
                updated_at,
                payment_method,
                payment_id,
                {"source": "synthetic", "seed": str(seed)},
            )
            payment_values = (
                payment_id,
                order_id,
                customer_id,
                amount,
                "USD",
                payment_method,
                payment_status,
                payment_created_at,
                payment_processed_at,
                payment_completed_at,
                failed_at,
                refunded_at,
                {"result": payment_status, "source": "synthetic"},
                Decimal("0.00"),
                f"TXN-{order_id.removeprefix('ORD-')}",
                {"source": "synthetic", "seed": str(seed)},
            )
            yield order_values, payment_values, order_status, payment_status


def insert_data(host: str, port: int, keyspace: str, days: int,
                orders_per_day: int, seed: int) -> dict:
    end_date = date.today()
    initialize_cassandra_schema([host], port=port, keyspace=keyspace)

    cluster = Cluster([host], port=port)
    session = cluster.connect(keyspace)
    order_statement = session.prepare(ORDER_INSERT)
    payment_statement = session.prepare(PAYMENT_INSERT)
    customer_statement = session.prepare(CUSTOMER_INSERT)
    product_statement = session.prepare(PRODUCT_ITEM_INSERT)
    counts = Counter()
    sample_ids = []
    inserted_customers = set()

    try:
        total = days * orders_per_day
        for index, (order_values, payment_values, order_status, payment_status) in enumerate(
            generated_rows(days, orders_per_day, seed, end_date), start=1
        ):
            customer_id = order_values[1]
            if customer_id not in inserted_customers:
                session.execute(customer_statement, generated_customer(customer_id, seed))
                inserted_customers.add(customer_id)
                counts["customers"] += 1
            session.execute(order_statement, order_values)
            session.execute(payment_statement, payment_values)
            counts["orders"] += 1
            counts["payments"] += 1
            counts[f"order_status:{order_status}"] += 1
            counts[f"payment_status:{payment_status}"] += 1
            if index in {1, total // 2, total}:
                sample_ids.append((order_values[0], payment_values[0], customer_id))
            if index % 1000 == 0 or index == total:
                print(f"Inserted {index:,}/{total:,} order/payment pairs")

        product_rows = list(generated_product_catalog(seed))
        for product_row in product_rows:
            session.execute(product_statement, product_row)
        counts["products"] = len(product_rows)
        counts["product_variants"] = len(product_rows)
        print(f"Inserted {len(product_rows):,} catalog rows across {len(CATEGORY_BRANDS)} categories")

        for order_id, payment_id, customer_id in sample_ids:
            order = session.execute(
                "SELECT order_id, payment_id FROM orders_table WHERE order_id = %s",
                (order_id,),
            ).one()
            payment = session.execute(
                "SELECT payment_id, order_id FROM payments_table WHERE payment_id = %s",
                (payment_id,),
            ).one()
            customer = session.execute(
                "SELECT customer_id, email, city FROM customers_table WHERE customer_id = %s",
                (customer_id,),
            ).one()
            if not order or order.payment_id != payment_id:
                raise RuntimeError(f"Order verification failed for {order_id}")
            if not payment or payment.order_id != order_id:
                raise RuntimeError(f"Payment verification failed for {payment_id}")
            if not customer or not customer.email.endswith("@example.com"):
                raise RuntimeError(f"Customer verification failed for {customer_id}")
    finally:
        cluster.shutdown()

    return dict(counts)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--orders-per-day", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261003)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9042)
    parser.add_argument("--keyspace", default="payments")
    parser.add_argument(
        "--products-only",
        action="store_true",
        help="Insert and verify the product catalog without generating orders or payments",
    )
    args = parser.parse_args()
    if not args.products_only and (args.days < 1 or args.orders_per_day < 1):
        parser.error("--days and --orders-per-day must both be positive")
    return args


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.products_only:
        category_counts = insert_product_catalog(
            host=arguments.host,
            port=arguments.port,
            keyspace=arguments.keyspace,
            seed=arguments.seed,
        )
        print(
            f"Verified {sum(category_counts.values()):,} product variants across "
            f"{len(category_counts)} categories: {category_counts}"
        )
        raise SystemExit(0)

    totals = insert_data(
        host=arguments.host,
        port=arguments.port,
        keyspace=arguments.keyspace,
        days=arguments.days,
        orders_per_day=arguments.orders_per_day,
        seed=arguments.seed,
    )
    print(
        f"Completed: {totals['customers']:,} customers, "
        f"{totals['orders']:,} orders, {totals['payments']:,} payments, "
        f"and {totals.get('products', 0):,} product catalog rows"
    )
    print("Status totals:")
    for key, value in sorted(totals.items()):
        if key.startswith(("order_status:", "payment_status:")):
            print(f"  {key}: {value:,}")
    print("Representative order/payment rows were read back and verified.")