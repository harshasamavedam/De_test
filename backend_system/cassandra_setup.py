"""Initialize Cassandra keyspace and tables for the local payments system."""

from cassandra.cluster import Cluster


def initialize_cassandra_schema(contact_points=None, port=9042, keyspace="payments"):
    """Create the keyspace and required tables if they do not already exist."""
    contact_points = contact_points or ["127.0.0.1"]

    cluster = Cluster(contact_points, port=port)
    session = cluster.connect()

    session.execute(
        f"""
        CREATE KEYSPACE IF NOT EXISTS {keyspace}
        WITH REPLICATION = {{ 'class': 'SimpleStrategy', 'replication_factor': 1 }}
        AND durable_writes = true
        """
    )

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {keyspace}.orders_table (
            order_id text,
            customer_id text,
            amount decimal,
            currency text,
            status text,
            created_at timestamp,
            updated_at timestamp,
            payment_method text,
            payment_id text,
            metadata map<text, text>,
            PRIMARY KEY ((order_id), created_at)
        )
        """
    )

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {keyspace}.customers_table (
            customer_id text PRIMARY KEY,
            first_name text,
            last_name text,
            email text,
            phone text,
            date_of_birth date,
            address_line text,
            city text,
            region text,
            postal_code text,
            country text,
            latitude double,
            longitude double,
            metadata map<text, text>
        )
        """
    )

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {keyspace}.payments_table (
            payment_id text,
            order_id text,
            customer_id text,
            amount decimal,
            currency text,
            payment_method text,
            status text,
            created_at timestamp,
            processed_at timestamp,
            completed_at timestamp,
            failed_at timestamp,
            refunded_at timestamp,
            gateway_response map<text, text>,
            gateway_fee decimal,
            transaction_reference text,
            metadata map<text, text>,
            PRIMARY KEY ((payment_id), created_at)
        )
        """
    )

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {keyspace}.product_item (
            category text,
            brand text,
            product_id text,
            product_name text,
            variant_id text,
            variant_name text,
            sku text,
            color text,
            size text,
            price decimal,
            cost decimal,
            stock int,
            warehouse text,
            is_active boolean,
            metadata map<text, text>,
            PRIMARY KEY ((category), brand, product_id, variant_id)
        )
        """
    )

    session.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {keyspace}.customer_order_items_by_customer (
            customer_id text,
            created_at timestamp,
            order_id text,
            product_id text,
            variant_id text,
            category text,
            brand text,
            product_name text,
            variant_name text,
            quantity int,
            unit_price decimal,
            order_status text,
            PRIMARY KEY ((customer_id), created_at, order_id, product_id, variant_id)
        ) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC, product_id ASC, variant_id ASC)
        """
    )

    cluster.shutdown()
    print(
        f"Initialized Cassandra keyspace '{keyspace}' with tables "
        "'customers_table', 'orders_table', 'payments_table', 'product_item', "
        "and 'customer_order_items_by_customer'."
    )


if __name__ == "__main__":
    initialize_cassandra_schema()
