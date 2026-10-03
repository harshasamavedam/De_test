"""
Data models for Orders Service
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from decimal import Decimal


class OrderStatus(str, Enum):
    """Order status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

    @classmethod
    def get_valid_transitions(cls, current_status: 'OrderStatus') -> List['OrderStatus']:
        """Get valid status transitions for a given status"""
        transitions = {
            OrderStatus.PENDING: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
            OrderStatus.PROCESSING: [OrderStatus.COMPLETED, OrderStatus.CANCELLED],
            OrderStatus.COMPLETED: [OrderStatus.REFUNDED],
            OrderStatus.CANCELLED: [],
            OrderStatus.REFUNDED: [],
        }
        return transitions.get(current_status, [])


class Order(BaseModel):
    """Order model representing a payment order"""
    order_id: str = Field(..., description="Unique order identifier")
    customer_id: str = Field(..., description="Customer identifier")
    amount: Decimal = Field(..., description="Order amount", ge=0)
    currency: str = Field(default="USD", description="Currency code")
    status: OrderStatus = Field(default=OrderStatus.PENDING, description="Order status")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    payment_method: Optional[str] = Field(None, description="Payment method used")
    payment_id: Optional[str] = Field(None, description="Associated payment identifier")
    metadata: dict = Field(default_factory=dict, description="Additional order metadata")

    @validator('order_id')
    def validate_order_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Order ID cannot be empty')
        return v.strip()

    @validator('customer_id')
    def validate_customer_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Customer ID cannot be empty')
        return v.strip()

    @validator('amount')
    def validate_amount(cls, v):
        if v < 0:
            raise ValueError('Amount cannot be negative')
        return v

    @validator('currency')
    def validate_currency(cls, v):
        if len(v) != 3 or not v.isalpha():
            raise ValueError('Currency must be 3-letter ISO code')
        return v.upper()

    @validator('status')
    def validate_status_transition(cls, v, values):
        if 'status' in values:
            current_status = values['status']
            valid_transitions = OrderStatus.get_valid_transitions(current_status)
            if v not in valid_transitions:
                raise ValueError(
                    f"Invalid status transition from {current_status} to {v}. "
                    f"Valid transitions: {[t.value for t in valid_transitions]}"
                )
        return v

    def is_terminal(self) -> bool:
        """Check if order is in a terminal state"""
        return self.status in [OrderStatus.CANCELLED, OrderStatus.COMPLETED, OrderStatus.REFUNDED]

    def can_be_cancelled(self) -> bool:
        """Check if order can be cancelled"""
        return self.status == OrderStatus.PENDING

    def can_be_refunded(self) -> bool:
        """Check if order can be refunded"""
        return self.status == OrderStatus.COMPLETED