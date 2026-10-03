"""
Main application entry point for Payments Orders System
"""

import asyncio
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from orders_service import OrdersService, OrdersRepository
from payments_service import PaymentsService, PaymentsRepository
from orders_service.models import OrderStatus
from payments_service.models import PaymentStatus, PaymentMethod


class PaymentsOrdersSystem:
    """Main application class orchestrating all services"""

    def __init__(self):
        # Initialize repositories
        self.orders_repository = OrdersRepository()
        self.payments_repository = PaymentsRepository()

        # Initialize services
        self.orders_service = OrdersService(self.orders_repository)
        self.payments_service = PaymentsService(self.payments_repository)

        # Connect to databases
        self._setup_database_connections()

    def _setup_database_connections(self):
        """Establish connections to all databases"""
        print("Setting up database connections...")
        self.orders_repository.connect()
        self.payments_repository.connect()
        print("Database connections established")

    def close_connections(self):
        """Close all database connections"""
        print("Closing database connections...")
        self.orders_repository.close()
        self.payments_repository.close()
        print("Database connections closed")

    # Orders Service Methods
    def create_order(self, customer_id: str, amount: float, currency: str = "USD",
                    payment_method: str = None, metadata: dict = None) -> Dict[str, Any]:
        """Create a new order"""
        try:
            order = self.orders_service.create_order(
                customer_id=customer_id,
                amount=amount,
                currency=currency,
                payment_method=payment_method,
                metadata=metadata
            )
            return {
                "success": True,
                "order": {
                    "order_id": order.order_id,
                    "customer_id": order.customer_id,
                    "amount": float(order.amount),
                    "currency": order.currency,
                    "status": order.status.value,
                    "created_at": order.created_at.isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order by ID"""
        try:
            order = self.orders_service.get_order(order_id)
            if order:
                return {
                    "success": True,
                    "order": {
                        "order_id": order.order_id,
                        "customer_id": order.customer_id,
                        "amount": float(order.amount),
                        "currency": order.currency,
                        "status": order.status.value,
                        "created_at": order.created_at.isoformat(),
                        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                        "payment_method": order.payment_method,
                        "payment_id": order.payment_id
                    }
                }
            else:
                return {
                    "success": False,
                    "error": "Order not found"
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def update_order_status(self, order_id: str, new_status: str) -> Dict[str, Any]:
        """Update order status"""
        try:
            status = OrderStatus(new_status)
            success = self.orders_service.update_order_status(order_id, status)
            return {
                "success": success,
                "order_id": order_id,
                "new_status": new_status
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an order"""
        try:
            success = self.orders_service.cancel_order(order_id)
            return {
                "success": success,
                "order_id": order_id,
                "action": "cancelled"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # Payments Service Methods
    def create_payment(self, order_id: str, customer_id: str, amount: float,
                      currency: str = "USD", payment_method: str = "credit_card",
                      metadata: dict = None) -> Dict[str, Any]:
        """Create a new payment"""
        try:
            method = PaymentMethod(payment_method)
            payment = self.payments_service.create_payment(
                order_id=order_id,
                customer_id=customer_id,
                amount=amount,
                currency=currency,
                payment_method=method,
                metadata=metadata
            )
            return {
                "success": True,
                "payment": {
                    "payment_id": payment.payment_id,
                    "order_id": payment.order_id,
                    "customer_id": payment.customer_id,
                    "amount": float(payment.amount),
                    "currency": payment.currency,
                    "payment_method": payment.payment_method.value,
                    "status": payment.status.value,
                    "created_at": payment.created_at.isoformat()
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def process_payment(self, payment_id: str) -> Dict[str, Any]:
        """Process a payment"""
        try:
            success = self.payments_service.process_payment(payment_id)
            return {
                "success": success,
                "payment_id": payment_id,
                "action": "processed"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def complete_payment(self, payment_id: str, gateway_response: dict = None,
                        gateway_fee: float = None, transaction_reference: str = None) -> Dict[str, Any]:
        """Complete a payment"""
        try:
            success = self.payments_service.complete_payment(
                payment_id=payment_id,
                gateway_response=gateway_response,
                gateway_fee=gateway_fee,
                transaction_reference=transaction_reference
            )
            return {
                "success": success,
                "payment_id": payment_id,
                "action": "completed"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def fail_payment(self, payment_id: str, failure_reason: str = None) -> Dict[str, Any]:
        """Fail a payment"""
        try:
            success = self.payments_service.fail_payment(payment_id, failure_reason)
            return {
                "success": success,
                "payment_id": payment_id,
                "action": "failed"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def refund_payment(self, payment_id: str) -> Dict[str, Any]:
        """Refund a payment"""
        try:
            success = self.payments_service.refund_payment(payment_id)
            return {
                "success": success,
                "payment_id": payment_id,
                "action": "refunded"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        try:
            orders = self.orders_service.get_all_orders(1000)
            payments = self.payments_service.get_all_payments(1000)

            # Calculate statistics
            total_orders = len(orders)
            total_payments = len(payments)
            completed_orders = len([o for o in orders if o.status == OrderStatus.COMPLETED])
            completed_payments = len([p for p in payments if p.status == PaymentStatus.COMPLETED])
            pending_orders = len([o for o in orders if o.status == OrderStatus.PENDING])
            processing_payments = len([p for p in payments if p.status == PaymentStatus.PROCESSING])

            return {
                "success": True,
                "statistics": {
                    "orders": {
                        "total": total_orders,
                        "completed": completed_orders,
                        "pending": pending_orders,
                        "cancelled": len([o for o in orders if o.status == OrderStatus.CANCELLED]),
                        "refunded": len([o for o in orders if o.status == OrderStatus.REFUNDED])
                    },
                    "payments": {
                        "total": total_payments,
                        "completed": completed_payments,
                        "processing": processing_payments,
                        "failed": len([p for p in payments if p.status == PaymentStatus.FAILED]),
                        "refunded": len([p for p in payments if p.status == PaymentStatus.REFUNDED]),
                        "cancelled": len([p for p in payments if p.status == PaymentStatus.CANCELLED])
                    }
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# FastAPI Application Setup
app = FastAPI(
    title="Payments Orders System API",
    description="Production-grade payments and orders management system",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the system
system = PaymentsOrdersSystem()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    system.close_connections()


# Orders API Endpoints
@app.post("/orders")
async def create_order(
    customer_id: str,
    amount: float,
    currency: str = "USD",
    payment_method: str = None,
    metadata: dict = None
):
    """Create a new order"""
    result = system.create_order(
        customer_id=customer_id,
        amount=amount,
        currency=currency,
        payment_method=payment_method,
        metadata=metadata
    )
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["error"])


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Get order by ID"""
    result = system.get_order(order_id)
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=404, detail=result["error"])


@app.put("/orders/{order_id}/status")
async def update_order_status(order_id: str, new_status: str):
    """Update order status"""
    result = system.update_order_status(order_id, new_status)
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["error"])


@app.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str):
    """Cancel an order"""
    result = system.cancel_order(order_id)
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["error"])


# Payments API Endpoints
@app.post("/payments")
async def create_payment(
    order_id: str,
    customer_id: str,
    amount: float,
    currency: str = "USD",
    payment_method: str = "credit_card",
    metadata: dict = None
):
    """Create a new payment"""
    result = system.create_payment(
        order_id=order_id,
        customer_id=customer_id,
        amount=amount,
        currency=currency,
        payment_method=payment_method,
        metadata=metadata
    )
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["error"])


@app.get("/payments/{payment_id}")
async def get_payment(payment_id: str):
    """Get payment by ID"""
    result = system.get_payment(payment_id)
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=404, detail=result["error"])


@app.post("/payments/{payment_id}/process")
async def process_payment(payment_id: str):
    """Process a payment"""
    result = system.process_payment(payment_id)
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["error"])


@app.post("/payments/{payment_id}/complete")
async def complete_payment(
    payment_id: str,
    gateway_response: dict = None,
    gateway_fee: float = None,
    transaction_reference: str = None
):
    """Complete a payment"""
    result = system.complete_payment(
        payment_id=payment_id,
        gateway_response=gateway_response,
        gateway_fee=gateway_fee,
        transaction_reference=transaction_reference
    )
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["error"])


@app.post("/payments/{payment_id}/fail")
async def fail_payment(payment_id: str, failure_reason: str = None):
    """Fail a payment"""
    result = system.fail_payment(payment_id, failure_reason)
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["error"])


@app.post("/payments/{payment_id}/refund")
async def refund_payment(payment_id: str):
    """Refund a payment"""
    result = system.refund_payment(payment_id)
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=400, detail=result["error"])


@app.get("/system/stats")
async def get_system_stats():
    """Get system statistics"""
    result = system.get_system_stats()
    if result["success"]:
        return result
    else:
        raise HTTPException(status_code=500, detail=result["error"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Payments Orders System API",
        "version": "1.0.0",
        "status": "running"
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)