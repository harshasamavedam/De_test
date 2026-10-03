"""Smoke-test Cassandra writes and reads for the payments system."""

from decimal import Decimal

from orders_service.models import Order, OrderStatus
from orders_service.repository import OrdersRepository
from payments_service.models import Payment, PaymentMethod, PaymentStatus
from payments_service.repository import PaymentsRepository


order_repo = OrdersRepository()
payment_repo = PaymentsRepository()

assert order_repo.connect(), "OrdersRepository failed to connect to Cassandra"
assert payment_repo.connect(), "PaymentsRepository failed to connect to Cassandra"

order = Order(
    order_id="ORD-VERIFY-001",
    customer_id="CUST-001",
    amount=Decimal("125.50"),
    currency="USD",
    status=OrderStatus.PENDING,
    payment_method="credit_card",
    metadata={"source": "verify"},
)

payment = Payment(
    payment_id="PAY-VERIFY-001",
    order_id="ORD-VERIFY-001",
    customer_id="CUST-001",
    amount=Decimal("125.50"),
    currency="USD",
    payment_method=PaymentMethod.CREDIT_CARD,
    status=PaymentStatus.PENDING,
    metadata={"source": "verify"},
)

assert order_repo.create_order(order), "Failed to insert order"
assert payment_repo.create_payment(payment), "Failed to insert payment"

stored_order = order_repo.get_order("ORD-VERIFY-001")
stored_payment = payment_repo.get_payment("PAY-VERIFY-001")

print({
    "order": {
        "order_id": stored_order.order_id,
        "customer_id": stored_order.customer_id,
        "amount": str(stored_order.amount),
        "status": stored_order.status.value,
    },
    "payment": {
        "payment_id": stored_payment.payment_id,
        "order_id": stored_payment.order_id,
        "customer_id": stored_payment.customer_id,
        "amount": str(stored_payment.amount),
        "status": stored_payment.status.value,
    },
})

order_repo.close()
payment_repo.close()
