"""
Repository layer for Orders Service - Cassandra database operations
"""

from typing import Optional, List
from datetime import datetime

try:
    from cassandra.cluster import Cluster
    from cassandra.query import dict_factory
    CASSANDRA_AVAILABLE = True
except Exception:  # pragma: no cover - fallback for unsupported Python envs
    Cluster = None
    dict_factory = None
    CASSANDRA_AVAILABLE = False

from .models import Order, OrderStatus


class OrdersRepository:
    """Repository for managing Order entities in Cassandra"""

    def __init__(self, contact_points: List[str] = None, port: int = 9042, keyspace: str = "payments"):
        """
        Initialize the repository with Cassandra connection

        Args:
            contact_points: List of Cassandra node addresses
            port: Cassandra native transport port
            keyspace: Target keyspace name
        """
        self.contact_points = contact_points or ["127.0.0.1"]
        self.port = port
        self.keyspace = keyspace
        self.cluster = None
        self.session = None

    def connect(self):
        """Establish connection to Cassandra cluster and initialize required schema."""
        if not CASSANDRA_AVAILABLE or Cluster is None:
            print("Cassandra driver is not available in this environment. Database features will be disabled until local Cassandra is configured.")
            return False

        try:
            self.cluster = Cluster(self.contact_points, port=self.port)
            self.session = self.cluster.connect()
            self._create_keyspace_if_missing()
            self.session = self.cluster.connect(self.keyspace)
            self.session.row_factory = dict_factory
            self._create_tables_if_missing()
            print(f"Connected to Cassandra cluster at {self.contact_points} and initialized keyspace '{self.keyspace}'")
            return True
        except Exception as e:
            print(f"Failed to connect to Cassandra: {e}")
            return False

    def _create_keyspace_if_missing(self):
        """Create the target keyspace if it does not exist."""
        query = f"""
        CREATE KEYSPACE IF NOT EXISTS {self.keyspace}
        WITH REPLICATION = {{ 'class': 'SimpleStrategy', 'replication_factor': 1 }}
        AND durable_writes = true
        """
        self.session.execute(query)

    def _create_tables_if_missing(self):
        """Create all required tables if they do not exist."""
        create_orders_table = f"""
        CREATE TABLE IF NOT EXISTS {self.keyspace}.orders_table (
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
        self.session.execute(create_orders_table)

    def close(self):
        """Close Cassandra connection"""
        if self.cluster:
            self.cluster.shutdown()
            print("Cassandra connection closed")

    def create_order(self, order: Order) -> bool:
        """
        Create a new order in Cassandra

        Args:
            order: Order object to create

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.session:
            print(f"Order creation skipped for {order.order_id}: Cassandra session not available")
            return False

        query = """
        INSERT INTO orders_table (
            order_id, customer_id, amount, currency, status,
            created_at, updated_at, payment_method, payment_id, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        try:
            self.session.execute(
                query,
                (
                    order.order_id,
                    order.customer_id,
                    order.amount,
                    order.currency,
                    order.status.value,
                    order.created_at,
                    order.updated_at,
                    order.payment_method,
                    order.payment_id,
                    order.metadata
                )
            )
            return True
        except Exception as e:
            print(f"Error creating order {order.order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Retrieve an order by its ID

        Args:
            order_id: Unique order identifier

        Returns:
            Order object if found, None otherwise
        """
        if not self.session:
            print(f"Order lookup skipped for {order_id}: Cassandra session not available")
            return None

        query = "SELECT * FROM orders_table WHERE order_id = %s"

        try:
            result = self.session.execute(query, (order_id,))
            row = result.one()

            if row:
                return self._row_to_order(row)
            return None
        except Exception as e:
            print(f"Error retrieving order {order_id}: {e}")
            return None

    def get_orders_by_customer(self, customer_id: str) -> List[Order]:
        """
        Retrieve all orders for a specific customer

        Args:
            customer_id: Customer identifier

        Returns:
            List of Order objects
        """
        query = "SELECT * FROM orders_table WHERE customer_id = %s ALLOW FILTERING"

        try:
            result = self.session.execute(query, (customer_id,))
            return [self._row_to_order(row) for row in result]
        except Exception as e:
            print(f"Error retrieving orders for customer {customer_id}: {e}")
            return []

    def update_order(self, order: Order) -> bool:
        """
        Update an existing order

        Args:
            order: Order object with updated fields

        Returns:
            bool: True if successful, False otherwise
        """
        query = """
        UPDATE orders_table SET
            customer_id = %s, amount = %s, currency = %s, status = %s,
            updated_at = %s, payment_method = %s, payment_id = %s, metadata = %s
        WHERE order_id = %s
        """

        try:
            self.session.execute(
                query,
                (
                    order.customer_id,
                    order.amount,
                    order.currency,
                    order.status.value,
                    order.updated_at,
                    order.payment_method,
                    order.payment_id,
                    order.metadata,
                    order.order_id
                )
            )
            return True
        except Exception as e:
            print(f"Error updating order {order.order_id}: {e}")
            return False

    def delete_order(self, order_id: str) -> bool:
        """
        Delete an order by its ID

        Args:
            order_id: Unique order identifier

        Returns:
            bool: True if successful, False otherwise
        """
        query = "DELETE FROM orders_table WHERE order_id = %s"

        try:
            self.session.execute(query, (order_id,))
            return True
        except Exception as e:
            print(f"Error deleting order {order_id}: {e}")
            return False

    def get_all_orders(self, limit: int = 100) -> List[Order]:
        """
        Retrieve all orders (paginated)

        Args:
            limit: Maximum number of orders to return

        Returns:
            List of Order objects
        """
        query = f"SELECT * FROM orders_table LIMIT {limit}"

        try:
            result = self.session.execute(query)
            return [self._row_to_order(row) for row in result]
        except Exception as e:
            print(f"Error retrieving all orders: {e}")
            return []

    def _row_to_order(self, row) -> Order:
        """
        Convert Cassandra row to Order object

        Args:
            row: Cassandra row object

        Returns:
            Order object
        """
        return Order(
            order_id=row['order_id'],
            customer_id=row['customer_id'],
            amount=row['amount'],
            currency=row['currency'],
            status=OrderStatus(row['status']),
            created_at=row['created_at'],
            updated_at=row.get('updated_at'),
            payment_method=row.get('payment_method'),
            payment_id=row.get('payment_id'),
            metadata=row.get('metadata', {})
        )