"""
Service layer for Orders Service - Business logic and orchestration
"""

from typing import Optional, List
from datetime import datetime
from .models import Order, OrderStatus
from .repository import OrdersRepository


class OrdersService:
    """Service for managing order lifecycle and business logic"""

    def __init__(self, repository: OrdersRepository):
        """
        Initialize the service with a repository

        Args:
            repository: OrdersRepository instance
        """
        self.repository = repository

    def create_order(self, customer_id: str, amount: float, currency: str = "USD",
                    payment_method: str = None, metadata: dict = None) -> Order:
        """
        Create a new order with validation

        Args:
            customer_id: Customer identifier
            amount: Order amount
            currency: Currency code (default: USD)
            payment_method: Payment method used
            metadata: Additional order metadata

        Returns:
            Created Order object

        Raises:
            ValueError: If validation fails
        """
        # Generate order ID (simplified - in production use UUID)
        order_id = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{hash(customer_id) % 10000:04d}"

        # Create order
        order = Order(
            order_id=order_id,
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            metadata=metadata or {}
        )

        # Save to database
        if self.repository.create_order(order):
            return order
        else:
            raise RuntimeError(f"Failed to create order {order_id}")

    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Retrieve an order by its ID

        Args:
            order_id: Unique order identifier

        Returns:
            Order object if found, None otherwise
        """
        return self.repository.get_order(order_id)

    def get_customer_orders(self, customer_id: str) -> List[Order]:
        """
        Retrieve all orders for a specific customer

        Args:
            customer_id: Customer identifier

        Returns:
            List of Order objects
        """
        return self.repository.get_orders_by_customer(customer_id)

    def update_order_status(self, order_id: str, new_status: OrderStatus) -> bool:
        """
        Update order status with validation

        Args:
            order_id: Unique order identifier
            new_status: New status to set

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If status transition is invalid
        """
        # Get current order
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Validate status transition
        valid_transitions = OrderStatus.get_valid_transitions(order.status)
        if new_status not in valid_transitions:
            raise ValueError(
                f"Invalid status transition from {order.status} to {new_status}. "
                f"Valid transitions: {[t.value for t in valid_transitions]}"
            )

        # Update order
        order.status = new_status
        order.updated_at = datetime.utcnow()

        return self.repository.update_order(order)

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order (only if it's pending)

        Args:
            order_id: Unique order identifier

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If order cannot be cancelled
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if not order.can_be_cancelled():
            raise ValueError(f"Order {order_id} cannot be cancelled (current status: {order.status})")

        return self.update_order_status(order_id, OrderStatus.CANCELLED)

    def complete_order(self, order_id: str, payment_id: str = None) -> bool:
        """
        Mark order as completed (payment processed)

        Args:
            order_id: Unique order identifier
            payment_id: Associated payment identifier

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If order cannot be completed
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if order.status != OrderStatus.PROCESSING:
            raise ValueError(f"Order {order_id} cannot be completed (current status: {order.status})")

        # Update order status and payment info
        order.status = OrderStatus.COMPLETED
        order.updated_at = datetime.utcnow()
        order.payment_id = payment_id

        return self.repository.update_order(order)

    def refund_order(self, order_id: str) -> bool:
        """
        Process order refund

        Args:
            order_id: Unique order identifier

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If order cannot be refunded
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if not order.can_be_refunded():
            raise ValueError(f"Order {order_id} cannot be refunded (current status: {order.status})")

        return self.update_order_status(order_id, OrderStatus.REFUNDED)

    def get_all_orders(self, limit: int = 100) -> List[Order]:
        """
        Retrieve all orders (paginated)

        Args:
            limit: Maximum number of orders to return

        Returns:
            List of Order objects
        """
        return self.repository.get_all_orders(limit)