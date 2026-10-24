"""Postgres schema for the shop domain: 1:1 port of the Cassandra model.

Same 25 tables, same columns, only the types are mapped
(`decimal` -> NUMERIC, `map<text, text>` -> JSONB, `timestamp` -> TIMESTAMPTZ).
Cassandra clustering order becomes explicit DESC indexes.

Deliberately constraint-light (primary keys + lookup indexes only, no FK /
CHECK / UNIQUE): the simulator plants referential and financial defects on
purpose, and constraints would reject them. See `shop/dirty.py`.
"""

from __future__ import annotations

from psycopg.types.json import Json


def adapt(value):
    """Wrap dict/list values for JSONB columns; pass everything else through."""
    if isinstance(value, (dict, list)):
        return Json(value)
    return value


def adapt_row(params: list) -> list:
    return [adapt(v) for v in params]

TABLE_DDL = [
    # --- identity & traffic -------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT,
        first_name TEXT,
        last_name TEXT,
        phone TEXT,
        date_of_birth DATE,
        country TEXT,
        is_active BOOLEAN,
        created_at TIMESTAMPTZ,
        metadata JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users_by_email (
        email TEXT PRIMARY KEY,
        user_id TEXT,
        created_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_addresses (
        user_id TEXT,
        address_id TEXT,
        label TEXT,
        full_name TEXT,
        line1 TEXT,
        line2 TEXT,
        city TEXT,
        region TEXT,
        postal_code TEXT,
        country TEXT,
        phone TEXT,
        is_default BOOLEAN,
        created_at TIMESTAMPTZ,
        PRIMARY KEY (user_id, address_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        anonymous_id TEXT,
        user_id TEXT,
        source TEXT,
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        referrer TEXT,
        channel TEXT,
        device TEXT,
        os TEXT,
        user_agent TEXT,
        country TEXT,
        ip_hash TEXT,
        landing_page TEXT,
        is_bounce BOOLEAN,
        started_at TIMESTAMPTZ,
        ended_at TIMESTAMPTZ,
        metadata JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions_by_anonymous (
        anonymous_id TEXT,
        started_at TIMESTAMPTZ,
        session_id TEXT,
        user_id TEXT,
        channel TEXT,
        source TEXT,
        device TEXT,
        country TEXT,
        PRIMARY KEY (anonymous_id, started_at, session_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions_by_user (
        user_id TEXT,
        started_at TIMESTAMPTZ,
        session_id TEXT,
        anonymous_id TEXT,
        channel TEXT,
        source TEXT,
        device TEXT,
        PRIMARY KEY (user_id, started_at, session_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS identity_map (
        anonymous_id TEXT PRIMARY KEY,
        user_id TEXT,
        first_seen TIMESTAMPTZ,
        linked_at TIMESTAMPTZ,
        link_source TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS identity_map_by_user (
        user_id TEXT,
        anonymous_id TEXT,
        first_seen TIMESTAMPTZ,
        linked_at TIMESTAMPTZ,
        PRIMARY KEY (user_id, anonymous_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        session_id TEXT,
        event_at TIMESTAMPTZ,
        event_id TEXT,
        user_id TEXT,
        anonymous_id TEXT,
        event_type TEXT,
        page TEXT,
        product_id TEXT,
        variant_id TEXT,
        cart_id TEXT,
        properties JSONB,
        PRIMARY KEY (session_id, event_at, event_id)
    )
    """,
    # --- catalog ------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS categories (
        category_id TEXT PRIMARY KEY,
        name TEXT,
        description TEXT,
        product_count INTEGER,
        created_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS products_by_category (
        category_id TEXT,
        product_id TEXT,
        product_name TEXT,
        brand TEXT,
        variant_count INTEGER,
        created_at TIMESTAMPTZ,
        PRIMARY KEY (category_id, product_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS variants_by_product (
        product_id TEXT,
        variant_id TEXT,
        category_id TEXT,
        product_name TEXT,
        variant_name TEXT,
        sku TEXT,
        attributes JSONB,
        price NUMERIC,
        discounted_price NUMERIC,
        currency TEXT,
        is_active BOOLEAN,
        created_at TIMESTAMPTZ,
        PRIMARY KEY (product_id, variant_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_item_by_id (
        variant_id TEXT PRIMARY KEY,
        product_id TEXT,
        category_id TEXT,
        product_name TEXT,
        variant_name TEXT,
        sku TEXT,
        attributes JSONB,
        price NUMERIC,
        discounted_price NUMERIC,
        currency TEXT,
        is_active BOOLEAN
    )
    """,
    # --- cart ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS carts (
        cart_id TEXT PRIMARY KEY,
        session_id TEXT,
        anonymous_id TEXT,
        user_id TEXT,
        status TEXT,
        currency TEXT,
        item_count INTEGER,
        subtotal NUMERIC,
        discount_pct NUMERIC,
        discount_amount NUMERIC,
        total NUMERIC,
        lucky_roll_id TEXT,
        converted_order_id TEXT,
        created_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ,
        metadata JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cart_by_session (
        session_id TEXT PRIMARY KEY,
        cart_id TEXT,
        user_id TEXT,
        status TEXT,
        updated_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cart_by_user (
        user_id TEXT,
        created_at TIMESTAMPTZ,
        cart_id TEXT,
        status TEXT,
        total NUMERIC,
        currency TEXT,
        PRIMARY KEY (user_id, created_at, cart_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cart_items (
        cart_id TEXT,
        variant_id TEXT,
        product_id TEXT,
        product_name TEXT,
        variant_name TEXT,
        attributes JSONB,
        quantity INTEGER,
        unit_price NUMERIC,
        unit_discounted_price NUMERIC,
        line_total NUMERIC,
        currency TEXT,
        added_at TIMESTAMPTZ,
        PRIMARY KEY (cart_id, variant_id)
    )
    """,
    # --- orders -------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        user_id TEXT,
        cart_id TEXT,
        session_id TEXT,
        anonymous_id TEXT,
        source TEXT,
        channel TEXT,
        status TEXT,
        currency TEXT,
        item_count INTEGER,
        subtotal NUMERIC,
        discount_pct NUMERIC,
        discount_amount NUMERIC,
        discount_reason TEXT,
        tax_amount NUMERIC,
        shipping_amount NUMERIC,
        total_amount NUMERIC,
        shipping_address JSONB,
        created_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orders_by_user (
        user_id TEXT,
        created_at TIMESTAMPTZ,
        order_id TEXT,
        status TEXT,
        total_amount NUMERIC,
        currency TEXT,
        item_count INTEGER,
        PRIMARY KEY (user_id, created_at, order_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS order_items (
        order_id TEXT,
        variant_id TEXT,
        product_id TEXT,
        product_name TEXT,
        variant_name TEXT,
        attributes JSONB,
        quantity INTEGER,
        unit_price NUMERIC,
        unit_discounted_price NUMERIC,
        line_total NUMERIC,
        currency TEXT,
        PRIMARY KEY (order_id, variant_id)
    )
    """,
    # --- payments -----------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS payments (
        payment_id TEXT PRIMARY KEY,
        order_id TEXT,
        user_id TEXT,
        attempt_no INTEGER,
        amount NUMERIC,
        currency TEXT,
        method TEXT,
        status TEXT,
        gateway TEXT,
        gateway_transaction_ref TEXT,
        gateway_fee NUMERIC,
        failure_reason TEXT,
        created_at TIMESTAMPTZ,
        processed_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        failed_at TIMESTAMPTZ,
        refunded_at TIMESTAMPTZ,
        metadata JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payments_by_order (
        order_id TEXT,
        attempt_no INTEGER,
        payment_id TEXT,
        status TEXT,
        amount NUMERIC,
        currency TEXT,
        method TEXT,
        gateway TEXT,
        created_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        failed_at TIMESTAMPTZ,
        PRIMARY KEY (order_id, attempt_no)
    )
    """,
    # --- lucky check --------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS lucky_rolls (
        scope_type TEXT,
        scope_id TEXT,
        roll_date DATE,
        rolled_value INTEGER,
        won BOOLEAN,
        discount_pct NUMERIC,
        cart_id TEXT,
        created_at TIMESTAMPTZ,
        PRIMARY KEY (scope_type, scope_id, roll_date)
    )
    """,
    # --- simulation metadata ------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS simulation_runs (
        run_id TEXT PRIMARY KEY,
        started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ,
        status TEXT,
        params JSONB,
        actuals JSONB,
        row_counts JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS injected_issues (
        run_id TEXT,
        issue_id TEXT,
        table_name TEXT,
        entity_id TEXT,
        column_name TEXT,
        issue_type TEXT,
        original_value TEXT,
        injected_value TEXT,
        created_at TIMESTAMPTZ,
        PRIMARY KEY (run_id, issue_id)
    )
    """,
]

# Ordering equivalents of the old Cassandra clustering keys, plus the two
# single-table lookups the API does that have no dedicated copy table.
INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS sessions_by_anonymous_order "
    "ON sessions_by_anonymous (anonymous_id, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS sessions_by_user_order "
    "ON sessions_by_user (user_id, started_at DESC)",
    "CREATE INDEX IF NOT EXISTS cart_by_user_order "
    "ON cart_by_user (user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS orders_by_user_order "
    "ON orders_by_user (user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS events_order "
    "ON events (session_id, event_at)",
    "CREATE INDEX IF NOT EXISTS sessions_by_anon_lookup ON sessions (anonymous_id)",
    "CREATE INDEX IF NOT EXISTS sessions_by_user_lookup ON sessions (user_id)",
]

TABLE_NAMES = [
    "users", "users_by_email", "user_addresses", "sessions",
    "sessions_by_anonymous", "sessions_by_user", "identity_map",
    "identity_map_by_user", "events", "categories", "products_by_category",
    "variants_by_product", "product_item_by_id", "carts", "cart_by_session",
    "cart_by_user", "cart_items", "orders", "orders_by_user", "order_items",
    "payments", "payments_by_order", "lucky_rolls", "simulation_runs",
    "injected_issues",
]

# Primary-key columns per table, mirroring the DDL above.
PRIMARY_KEYS = {
    "users": ("user_id",),
    "users_by_email": ("email",),
    "user_addresses": ("user_id", "address_id"),
    "sessions": ("session_id",),
    "sessions_by_anonymous": ("anonymous_id", "started_at", "session_id"),
    "sessions_by_user": ("user_id", "started_at", "session_id"),
    "identity_map": ("anonymous_id",),
    "identity_map_by_user": ("user_id", "anonymous_id"),
    "events": ("session_id", "event_at", "event_id"),
    "categories": ("category_id",),
    "products_by_category": ("category_id", "product_id"),
    "variants_by_product": ("product_id", "variant_id"),
    "product_item_by_id": ("variant_id",),
    "carts": ("cart_id",),
    "cart_by_session": ("session_id",),
    "cart_by_user": ("user_id", "created_at", "cart_id"),
    "cart_items": ("cart_id", "variant_id"),
    "orders": ("order_id",),
    "orders_by_user": ("user_id", "created_at", "order_id"),
    "order_items": ("order_id", "variant_id"),
    "payments": ("payment_id",),
    "payments_by_order": ("order_id", "attempt_no"),
    "lucky_rolls": ("scope_type", "scope_id", "roll_date"),
    "simulation_runs": ("run_id",),
    "injected_issues": ("run_id", "issue_id"),
}


def insert_sql(table: str, columns: tuple | list, upsert: bool = True) -> str:
    """Build a positional INSERT for `table` (parameters are `%s`).

    With `upsert=True` (default) the statement becomes an upsert matching
    Cassandra's last-write-wins semantics, which the simulator and API rely
    on (e.g. a second abandoned cart re-points `cart_by_session`).
    """
    cols = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    if not upsert:
        return sql
    pk = PRIMARY_KEYS[table]
    non_pk = [c for c in columns if c not in pk]
    if not non_pk:
        return sql + f" ON CONFLICT ({', '.join(pk)}) DO NOTHING"
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk)
    return sql + f" ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {sets}"


def create_schema(conn) -> list[str]:
    """Create all tables + indexes. Returns the table names."""
    with conn.cursor() as cur:
        for ddl in TABLE_DDL:
            cur.execute(ddl)
        for ddl in INDEX_DDL:
            cur.execute(ddl)
    return list(TABLE_NAMES)


def reset_schema(conn) -> list[str]:
    """Drop everything in `public` and recreate. Returns the table names."""
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE")
        cur.execute("CREATE SCHEMA public")
    return create_schema(conn)
