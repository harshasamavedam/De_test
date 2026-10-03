"""
Service layer for Payments Service - Business logic and orchestration
"""

from typing import Optional, List
from datetime import datetime
from .models import Payment, PaymentStatus, PaymentMethod
from .repository import PaymentsRepository


class PaymentsService:
    """Service for managing payment processing and validation"""

    def __init__(self, repository: PaymentsRepository):
        """
        Initialize the service with a repository

        Args:
            repository: PaymentsRepository instance
        """
        self.repository = repository

    def create_payment(self, order_id: str, customer_id: str, amount: float,
                      currency: str = "USD", payment_method: PaymentMethod = PaymentMethod.CREDIT_CARD,
                      metadata: dict = None) -> Payment:
        """
        Create a new payment with validation

        Args:
            order_id: Order identifier
            customer_id: Customer identifier
            amount: Payment amount
            currency: Currency code (default: USD)
            payment_method: Payment method used (default: CREDIT_CARD)
            metadata: Additional payment metadata

        Returns:
            Created Payment object

        Raises:
            ValueError: If validation fails
        """
        # Generate payment ID (simplified - in production use UUID)
        payment_id = f"PAY-{datetime.utcnow().strftime('%Y%m%d')}-{hash(order_id) % 10000:04d}"

        # Create payment
        payment = Payment(
            payment_id=payment_id,
            order_id=order_id,
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            metadata=metadata or {}
        )

        # Save to database
        if self.repository.create_payment(payment):
            return payment
        else:
            raise RuntimeError(f"Failed to create payment {payment_id}")

    def get_payment(self, payment_id: str) -> Optional[Payment]:
        """
        Retrieve a payment by its ID

        Args:
            payment_id: Unique payment identifier

        Returns:
            Payment object if found, None otherwise
        """
        return self.repository.get_payment(payment_id)

    def get_order_payments(self, order_id: str) -> List[Payment]:
        """
        Retrieve all payments for a specific order

        Args:
            order_id: Order identifier

        Returns:
            List of Payment objects
        """
        return self.repository.get_payments_by_order(order_id)

    def get_customer_payments(self, customer_id: str) -> List[Payment]:
        """
        Retrieve all payments for a specific customer

        Args:
            customer_id: Customer identifier

        Returns:
            List of Payment objects
        """
        return self.repository.get_payments_by_customer(customer_id)

    def process_payment(self, payment_id: str) -> bool:
        """
        Process a payment (move from pending to processing)

        Args:
            payment_id: Unique payment identifier

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If payment cannot be processed
        """
        payment = self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status != PaymentStatus.PENDING:
            raise ValueError(f"Payment {payment_id} cannot be processed (current status: {payment.status})")

        # Update payment status
        payment.status = PaymentStatus.PROCESSING
        payment.processed_at = datetime.utcnow()

        return self.repository.update_payment(payment)

    def complete_payment(self, payment_id: str, gateway_response: dict = None,
                        gateway_fee: float = None, transaction_reference: str = None) -> bool:
        """
        Complete a payment (move from processing to completed)

        Args:
            payment_id: Unique payment identifier
            gateway_response: Payment gateway response data
            gateway_fee: Payment gateway fee
            transaction_reference: External transaction reference

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If payment cannot be completed
        """
        payment = self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status != PaymentStatus.PROCESSING:
            raise ValueError(f"Payment {payment_id} cannot be completed (current status: {payment.status})")

        # Update payment status and gateway info
        payment.status = PaymentStatus.COMPLETED
        payment.completed_at = datetime.utcnow()
        payment.gateway_response = gateway_response
        payment.gateway_fee = gateway_fee
        payment.transaction_reference = transaction_reference

        return self.repository.update_payment(payment)

    def fail_payment(self, payment_id: str, failure_reason: str = None) -> bool:
        """
        Mark payment as failed

        Args:
            payment_id: Unique payment identifier
            failure_reason: Reason for payment failure

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If payment cannot be failed
        """
        payment = self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status == PaymentStatus.FAILED:
            raise ValueError(f"Payment {payment_id} is already failed")

        # Update payment status
        payment.status = PaymentStatus.FAILED
        payment.failed_at = datetime.utcnow()
        payment.gateway_response = payment.gateway_response or {}
        payment.gateway_response['failure_reason'] = failure_reason

        return self.repository.update_payment(payment)

    def refund_payment(self, payment_id: str) -> bool:
        """
        Process payment refund

        Args:
            payment_id: Unique payment identifier

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If payment cannot be refunded
        """
        payment = self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if not payment.can_be_refunded():
            raise ValueError(f"Payment {payment_id} cannot be refunded (current status: {payment.status})")

        # Update payment status
        payment.status = PaymentStatus.REFUNDED
        payment.refunded_at = datetime.utcnow()

        return self.repository.update_payment(payment)

    def cancel_payment(self, payment_id: str) -> bool:
        """
        Cancel a payment

        Args:
            payment_id: Unique payment identifier

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If payment cannot be cancelled
        """
        payment = self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if payment.status == PaymentStatus.CANCELLED:
            raise ValueError(f"Payment {payment_id} is already cancelled")

        # Update payment status
        payment.status = PaymentStatus.CANCELLED

        return self.repository.update_payment(payment)

    def retry_payment(self, payment_id: str) -> bool:
        """
        Retry a failed payment

        Args:
            payment_id: Unique payment identifier

        Returns:
            bool: True if successful, False otherwise

        Raises:
            ValueError: If payment cannot be retried
        """
        payment = self.get_payment(payment_id)
        if not payment:
            raise ValueError(f"Payment {payment_id} not found")

        if not payment.can_be_retried():
            raise ValueError(f"Payment {payment_id} cannot be retried (current status: {payment.status})")

        # Reset payment status to pending
        payment.status = PaymentStatus.PENDING
        payment.failed_at = None

        return self.repository.update_payment(payment)

    def get_all_payments(self, limit: int = 100) -> List[Payment]:
        """
        Retrieve all payments (paginated)

        Args:
            limit: Maximum number of payments to return

        Returns:
            List of Payment objects
        """
        return self.repository.get_all_payments(limit)