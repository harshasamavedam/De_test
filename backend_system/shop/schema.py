"""Cassandra keyspace + table DDL and prepared-statement CQL for the shop domain.

The model is query-first: every table exists to serve a specific read pattern,
so data is denormalised across several tables on write.
"""

from __future__ import annotations

KEYSPACE = "shop"

CREATE_KEYSPACE = """
CREATE KEYSPACE IF NOT EXISTS {keyspace}
WITH REPLICATION = {{ 'class': 'SimpleStrategy', 'replication_factor': 1 }}
AND durable_writes = true
"""

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

TABLE_DDL = [
    # --- identity & traffic -------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.users (
        user_id text PRIMARY KEY,
        email text,
        first_name text,
        last_name text,
        phone text,
        date_of_birth date,
        country text,
        is_active boolean,
        created_at timestamp,
        metadata map<text, text>
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.users_by_email (
        email text PRIMARY KEY,
        user_id text,
        created_at timestamp
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.user_addresses (
        user_id text,
        address_id text,
        label text,
        full_name text,
        line1 text,
        line2 text,
        city text,
        region text,
        postal_code text,
        country text,
        phone text,
        is_default boolean,
        created_at timestamp,
        PRIMARY KEY ((user_id), address_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.sessions (
        session_id text PRIMARY KEY,
        anonymous_id text,
        user_id text,
        source text,
        utm_source text,
        utm_medium text,
        utm_campaign text,
        referrer text,
        channel text,
        device text,
        os text,
        user_agent text,
        country text,
        ip_hash text,
        landing_page text,
        is_bounce boolean,
        started_at timestamp,
        ended_at timestamp,
        metadata map<text, text>
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.sessions_by_anonymous (
        anonymous_id text,
        started_at timestamp,
        session_id text,
        user_id text,
        channel text,
        source text,
        device text,
        country text,
        PRIMARY KEY ((anonymous_id), started_at, session_id)
    ) WITH CLUSTERING ORDER BY (started_at DESC, session_id ASC)
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.sessions_by_user (
        user_id text,
        started_at timestamp,
        session_id text,
        anonymous_id text,
        channel text,
        source text,
        device text,
        PRIMARY KEY ((user_id), started_at, session_id)
    ) WITH CLUSTERING ORDER BY (started_at DESC, session_id ASC)
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.identity_map (
        anonymous_id text PRIMARY KEY,
        user_id text,
        first_seen timestamp,
        linked_at timestamp,
        link_source text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.identity_map_by_user (
        user_id text,
        anonymous_id text,
        first_seen timestamp,
        linked_at timestamp,
        PRIMARY KEY ((user_id), anonymous_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.events (
        session_id text,
        event_at timestamp,
        event_id text,
        user_id text,
        anonymous_id text,
        event_type text,
        page text,
        product_id text,
        variant_id text,
        cart_id text,
        properties map<text, text>,
        PRIMARY KEY ((session_id), event_at, event_id)
    )
    """,
    # --- catalog ------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.categories (
        category_id text PRIMARY KEY,
        name text,
        description text,
        product_count int,
        created_at timestamp
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.products_by_category (
        category_id text,
        product_id text,
        product_name text,
        brand text,
        variant_count int,
        created_at timestamp,
        PRIMARY KEY ((category_id), product_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.variants_by_product (
        product_id text,
        variant_id text,
        category_id text,
        product_name text,
        variant_name text,
        sku text,
        attributes map<text, text>,
        price decimal,
        discounted_price decimal,
        currency text,
        is_active boolean,
        created_at timestamp,
        PRIMARY KEY ((product_id), variant_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.product_item_by_id (
        variant_id text PRIMARY KEY,
        product_id text,
        category_id text,
        product_name text,
        variant_name text,
        sku text,
        attributes map<text, text>,
        price decimal,
        discounted_price decimal,
        currency text,
        is_active boolean
    )
    """,
    # --- cart ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.carts (
        cart_id text PRIMARY KEY,
        session_id text,
        anonymous_id text,
        user_id text,
        status text,
        currency text,
        item_count int,
        subtotal decimal,
        discount_pct decimal,
        discount_amount decimal,
        total decimal,
        lucky_roll_id text,
        converted_order_id text,
        created_at timestamp,
        updated_at timestamp,
        metadata map<text, text>
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.cart_by_session (
        session_id text PRIMARY KEY,
        cart_id text,
        user_id text,
        status text,
        updated_at timestamp
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.cart_by_user (
        user_id text,
        created_at timestamp,
        cart_id text,
        status text,
        total decimal,
        currency text,
        PRIMARY KEY ((user_id), created_at, cart_id)
    ) WITH CLUSTERING ORDER BY (created_at DESC, cart_id ASC)
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.cart_items (
        cart_id text,
        variant_id text,
        product_id text,
        product_name text,
        variant_name text,
        attributes map<text, text>,
        quantity int,
        unit_price decimal,
        unit_discounted_price decimal,
        line_total decimal,
        currency text,
        added_at timestamp,
        PRIMARY KEY ((cart_id), variant_id)
    )
    """,
    # --- orders -------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.orders (
        order_id text PRIMARY KEY,
        user_id text,
        cart_id text,
        session_id text,
        anonymous_id text,
        source text,
        channel text,
        status text,
        currency text,
        item_count int,
        subtotal decimal,
        discount_pct decimal,
        discount_amount decimal,
        discount_reason text,
        tax_amount decimal,
        shipping_amount decimal,
        total_amount decimal,
        shipping_address map<text, text>,
        created_at timestamp,
        updated_at timestamp
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.orders_by_user (
        user_id text,
        created_at timestamp,
        order_id text,
        status text,
        total_amount decimal,
        currency text,
        item_count int,
        PRIMARY KEY ((user_id), created_at, order_id)
    ) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC)
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.order_items (
        order_id text,
        variant_id text,
        product_id text,
        product_name text,
        variant_name text,
        attributes map<text, text>,
        quantity int,
        unit_price decimal,
        unit_discounted_price decimal,
        line_total decimal,
        currency text,
        PRIMARY KEY ((order_id), variant_id)
    )
    """,
    # --- payments -----------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.payments (
        payment_id text PRIMARY KEY,
        order_id text,
        user_id text,
        attempt_no int,
        amount decimal,
        currency text,
        method text,
        status text,
        gateway text,
        gateway_transaction_ref text,
        gateway_fee decimal,
        failure_reason text,
        created_at timestamp,
        processed_at timestamp,
        completed_at timestamp,
        failed_at timestamp,
        refunded_at timestamp,
        metadata map<text, text>
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.payments_by_order (
        order_id text,
        attempt_no int,
        payment_id text,
        status text,
        amount decimal,
        currency text,
        method text,
        gateway text,
        created_at timestamp,
        completed_at timestamp,
        failed_at timestamp,
        PRIMARY KEY ((order_id), attempt_no)
    )
    """,
    # --- lucky check --------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.lucky_rolls (
        scope_type text,
        scope_id text,
        roll_date date,
        rolled_value int,
        won boolean,
        discount_pct decimal,
        cart_id text,
        created_at timestamp,
        PRIMARY KEY ((scope_type, scope_id), roll_date)
    )
    """,
    # --- simulation metadata ------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.simulation_runs (
        run_id text PRIMARY KEY,
        started_at timestamp,
        finished_at timestamp,
        status text,
        params map<text, text>,
        actuals map<text, text>,
        row_counts map<text, bigint>
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS {keyspace}.injected_issues (
        run_id text,
        issue_id text,
        table_name text,
        entity_id text,
        column_name text,
        issue_type text,
        original_value text,
        injected_value text,
        created_at timestamp,
        PRIMARY KEY ((run_id), issue_id)
    )
    """,
]

# ---------------------------------------------------------------------------
# INSERT statements (positional, prepared)
# ---------------------------------------------------------------------------

INSERTS = {
    "users": """
        INSERT INTO users (user_id, email, first_name, last_name, phone,
            date_of_birth, country, is_active, created_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "users_by_email": """
        INSERT INTO users_by_email (email, user_id, created_at) VALUES (?, ?, ?)
    """,
    "user_addresses": """
        INSERT INTO user_addresses (user_id, address_id, label, full_name, line1,
            line2, city, region, postal_code, country, phone, is_default, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "sessions": """
        INSERT INTO sessions (session_id, anonymous_id, user_id, source, utm_source,
            utm_medium, utm_campaign, referrer, channel, device, os, user_agent,
            country, ip_hash, landing_page, is_bounce, started_at, ended_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "sessions_by_anonymous": """
        INSERT INTO sessions_by_anonymous (anonymous_id, started_at, session_id,
            user_id, channel, source, device, country)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "sessions_by_user": """
        INSERT INTO sessions_by_user (user_id, started_at, session_id,
            anonymous_id, channel, source, device)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    "identity_map": """
        INSERT INTO identity_map (anonymous_id, user_id, first_seen, linked_at,
            link_source)
        VALUES (?, ?, ?, ?, ?)
    """,
    "identity_map_by_user": """
        INSERT INTO identity_map_by_user (user_id, anonymous_id, first_seen,
            linked_at)
        VALUES (?, ?, ?, ?)
    """,
    "events": """
        INSERT INTO events (session_id, event_at, event_id, user_id, anonymous_id,
            event_type, page, product_id, variant_id, cart_id, properties)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "categories": """
        INSERT INTO categories (category_id, name, description, product_count,
            created_at)
        VALUES (?, ?, ?, ?, ?)
    """,
    "products_by_category": """
        INSERT INTO products_by_category (category_id, product_id, product_name,
            brand, variant_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
    "variants_by_product": """
        INSERT INTO variants_by_product (product_id, variant_id, category_id,
            product_name, variant_name, sku, attributes, price, discounted_price,
            currency, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "product_item_by_id": """
        INSERT INTO product_item_by_id (variant_id, product_id, category_id,
            product_name, variant_name, sku, attributes, price, discounted_price,
            currency, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "carts": """
        INSERT INTO carts (cart_id, session_id, anonymous_id, user_id, status,
            currency, item_count, subtotal, discount_pct, discount_amount, total,
            lucky_roll_id, converted_order_id, created_at, updated_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "cart_by_session": """
        INSERT INTO cart_by_session (session_id, cart_id, user_id, status,
            updated_at)
        VALUES (?, ?, ?, ?, ?)
    """,
    "cart_by_user": """
        INSERT INTO cart_by_user (user_id, created_at, cart_id, status, total,
            currency)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
    "cart_items": """
        INSERT INTO cart_items (cart_id, variant_id, product_id, product_name,
            variant_name, attributes, quantity, unit_price, unit_discounted_price,
            line_total, currency, added_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "orders": """
        INSERT INTO orders (order_id, user_id, cart_id, session_id, anonymous_id,
            source, channel, status, currency, item_count, subtotal, discount_pct,
            discount_amount, discount_reason, tax_amount, shipping_amount,
            total_amount, shipping_address, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "orders_by_user": """
        INSERT INTO orders_by_user (user_id, created_at, order_id, status,
            total_amount, currency, item_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    "order_items": """
        INSERT INTO order_items (order_id, variant_id, product_id, product_name,
            variant_name, attributes, quantity, unit_price, unit_discounted_price,
            line_total, currency)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "payments": """
        INSERT INTO payments (payment_id, order_id, user_id, attempt_no, amount,
            currency, method, status, gateway, gateway_transaction_ref,
            gateway_fee, failure_reason, created_at, processed_at, completed_at,
            failed_at, refunded_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "payments_by_order": """
        INSERT INTO payments_by_order (order_id, attempt_no, payment_id, status,
            amount, currency, method, gateway, created_at, completed_at, failed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "lucky_rolls": """
        INSERT INTO lucky_rolls (scope_type, scope_id, roll_date, rolled_value,
            won, discount_pct, cart_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    "simulation_runs": """
        INSERT INTO simulation_runs (run_id, started_at, finished_at, status,
            params, actuals, row_counts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    "injected_issues": """
        INSERT INTO injected_issues (run_id, issue_id, table_name, entity_id,
            column_name, issue_type, original_value, injected_value, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
}


def create_schema(session, keyspace: str = KEYSPACE) -> list[str]:
    """Create the keyspace and all tables. Returns the list of table names."""
    session.execute(CREATE_KEYSPACE.format(keyspace=keyspace))
    session.set_keyspace(keyspace)
    tables = []
    for ddl in TABLE_DDL:
        # Each DDL block starts with "CREATE TABLE IF NOT EXISTS <keyspace>.<name>".
        name = ddl.split("EXISTS", 1)[1].split(".", 1)[1].split("(", 1)[0].strip()
        session.execute(ddl.format(keyspace=keyspace))
        tables.append(name)
    return tables


def drop_keyspace(session, keyspace: str = KEYSPACE) -> None:
    session.execute(f"DROP KEYSPACE IF EXISTS {keyspace}")
