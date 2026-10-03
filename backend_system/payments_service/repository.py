"""
Repository layer for Payments Service - Cassandra database operations
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

from .models import Payment, PaymentStatus, PaymentMethod


class PaymentsRepository:
    """Repository for managing Payment entities in Cassandra"""

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
        create_payments_table = f"""
        CREATE TABLE IF NOT EXISTS {self.keyspace}.payments_table (
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
        self.session.execute(create_payments_table)

    def close(self):
        """Close Cassandra connection"""
        if self.cluster:
            self.cluster.shutdown()
            print("Cassandra connection closed")

    def create_payment(self, payment: Payment) -> bool:
        """
        Create a new payment in Cassandra

        Args:
            payment: Payment object to create

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.session:
            print(f"Payment creation skipped for {payment.payment_id}: Cassandra session not available")
            return False

        query = """
        INSERT INTO payments_table (
            payment_id, order_id, customer_id, amount, currency,
            payment_method, status, created_at, processed_at,
            completed_at, failed_at, refunded_at, gateway_response,
            gateway_fee, transaction_reference, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        try:
            self.session.execute(
                query,
                (
                    payment.payment_id,
                    payment.order_id,
                    payment.customer_id,
                    payment.amount,
                    payment.currency,
                    payment.payment_method.value,
                    payment.status.value,
                    payment.created_at,
                    payment.processed_at,
                    payment.completed_at,
                    payment.failed_at,
                    payment.refunded_at,
                    payment.gateway_response,
                    payment.gateway_fee,
                    payment.transaction_reference,
                    payment.metadata
                )
            )
            return True
        except Exception as e:
            print(f"Error creating payment {payment.payment_id}: {e}")
            return False

    def get_payment(self, payment_id: str) -> Optional[Payment]:
        """
        Retrieve a payment by its ID

        Args:
            payment_id: Unique payment identifier

        Returns:
            Payment object if found, None otherwise
        """
        if not self.session:
            print(f"Payment lookup skipped for {payment_id}: Cassandra session not available")
            return None

        query = "SELECT * FROM payments_table WHERE payment_id = %s"

        try:
            result = self.session.execute(query, (payment_id,))
            row = result.one()

            if row:
                return self._row_to_payment(row)
            return None
        except Exception as e:
            print(f"Error retrieving payment {payment_id}: {e}")
            return None

    def get_payments_by_order(self, order_id: str) -> List[Payment]:
        """
        Retrieve all payments for a specific order

        Args:
            order_id: Order identifier

        Returns:
            List of Payment objects
        """
        query = "SELECT * FROM payments_table WHERE order_id = %s ALLOW FILTERING"

        try:
            result = self.session.execute(query, (order_id,))
            return [self._row_to_payment(row) for row in result]
        except Exception as e:
            print(f"Error retrieving payments for order {order_id}: {e}")
            return []

    def get_payments_by_customer(self, customer_id: str) -> List[Payment]:
        """
        Retrieve all payments for a specific customer

        Args:
            customer_id: Customer identifier

        Returns:
            List of Payment objects
        """
        query = "SELECT * FROM payments_table WHERE customer_id = %s ALLOW FILTERING"

        try:
            result = self.session.execute(query, (customer_id,))
            return [self._row_to_payment(row) for row in result]
        except Exception as e:
            print(f"Error retrieving payments for customer {customer_id}: {e}")
            return []

    def update_payment(self, payment: Payment) -> bool:
        """
        Update an existing payment

        Args:
            payment: Payment object with updated fields

        Returns:
            bool: True if successful, False otherwise
        """
        query = """
        UPDATE payments_table SET
            order_id = %s, customer_id = %s, amount = %s, currency = %s,
            payment_method = %s, status = %s, created_at = %s,
            processed_at = %s, completed_at = %s, failed_at = %s,
            refunded_at = %s, gateway_response = %s, gateway_fee = %s,
            transaction_reference = %s, metadata = %s
        WHERE payment_id = %s
        """

        try:
            self.session.execute(
                query,
                (
                    payment.order_id,
                    payment.customer_id,
                    payment.amount,
                    payment.currency,
                    payment.payment_method.value,
                    payment.status.value,
                    payment.created_at,
                    payment.processed_at,
                    payment.completed_at,
                    payment.failed_at,
                    payment.refunded_at,
                    payment.gateway_response,
                    payment.gateway_fee,
                    payment.transaction_reference,
                    payment.metadata,
                    payment.payment_id
                )
            )
            return True
        except Exception as e:
            print(f"Error updating payment {payment.payment_id}: {e}")
            return False

    def delete_payment(self, payment_id: str) -> bool:
        """
        Delete a payment by its ID

        Args:
            payment_id: Unique payment identifier

        Returns:
            bool: True if successful, False otherwise
        """
        query = "DELETE FROM payments_table WHERE payment_id = %s"

        try:
            self.session.execute(query, (payment_id,))
            return True
        except Exception as e:
            print(f"Error deleting payment {payment_id}: {e}")
            return False

    def get_all_payments(self, limit: int = 100) -> List[Payment]:
        """
        Retrieve all payments (paginated)

        Args:
            limit: Maximum number of payments to return

        Returns:
            List of Payment objects
        """
        query = f"SELECT * FROM payments_table LIMIT {limit}"

        try:
            result = self.session.execute(query)
            return [self._row_to_payment(row) for row in result]
        except Exception as e:
            print(f"Error retrieving all payments: {e}")
            return []

    def _row_to_payment(self, row) -> Payment:
        """
        Convert Cassandra row to Payment object

        Args:
            row: Cassandra row object

        Returns:
            Payment object
        """
        return Payment(
            payment_id=row['payment_id'],
            order_id=row['order_id'],
            customer_id=row['customer_id'],
            amount=row['amount'],
            currency=row['currency'],
            payment_method=PaymentMethod(row['payment_method']),
            status=PaymentStatus(row['status']),
            created_at=row['created_at'],
            processed_at=row.get('processed_at'),
            completed_at=row.get('completed_at'),
            failed_at=row.get('failed_at'),
            refunded_at=row.get('refunded_at'),
            gateway_response=row.get('gateway_response'),
            gateway_fee=row.get('gateway_fee'),
            transaction_reference=row.get('transaction_reference'),
            metadata=row.get('metadata', {})
        )