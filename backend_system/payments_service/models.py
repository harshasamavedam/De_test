"""
Data models for Payments Service
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from decimal import Decimal


class PaymentMethod(str, Enum):
    """Payment method enumeration"""
    CREDIT_CARD = "credit_card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"
    DIGITAL_WALLET = "digital_wallet"
    CRYPTO = "crypto"

    @property
    def is_card_payment(self) -> bool:
        """Check if payment method is a card payment"""
        return self == PaymentMethod.CREDIT_CARD

    @property
    def requires_verification(self) -> bool:
        """Check if payment method requires additional verification"""
        return self in [PaymentMethod.CREDIT_CARD, PaymentMethod.PAYPAL]


class PaymentStatus(str, Enum):
    """Payment status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

    @classmethod
    def get_valid_transitions(cls, current_status: 'PaymentStatus') -> List['PaymentStatus']:
        """Get valid status transitions for a given status"""
        transitions = {
            PaymentStatus.PENDING: [PaymentStatus.PROCESSING, PaymentStatus.CANCELLED],
            PaymentStatus.PROCESSING: [PaymentStatus.COMPLETED, PaymentStatus.FAILED],
            PaymentStatus.COMPLETED: [PaymentStatus.REFUNDED],
            PaymentStatus.FAILED: [PaymentStatus.PENDING],
            PaymentStatus.REFUNDED: [],
            PaymentStatus.CANCELLED: [],
        }
        return transitions.get(current_status, [])


class Payment(BaseModel):
    """Payment model representing a payment transaction"""
    payment_id: str = Field(..., description="Unique payment identifier")
    order_id: str = Field(..., description="Associated order identifier")
    customer_id: str = Field(..., description="Customer identifier")
    amount: Decimal = Field(..., description="Payment amount", ge=0)
    currency: str = Field(default="USD", description="Currency code")
    payment_method: PaymentMethod = Field(..., description="Payment method used")
    status: PaymentStatus = Field(default=PaymentStatus.PENDING, description="Payment status")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    processed_at: Optional[datetime] = Field(None, description="Processing timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    failed_at: Optional[datetime] = Field(None, description="Failure timestamp")
    refunded_at: Optional[datetime] = Field(None, description="Refund timestamp")
    gateway_response: Optional[dict] = Field(None, description="Payment gateway response")
    gateway_fee: Optional[Decimal] = Field(None, description="Payment gateway fee")
    transaction_reference: Optional[str] = Field(None, description="External transaction reference")
    metadata: dict = Field(default_factory=dict, description="Additional payment metadata")

    @validator('payment_id')
    def validate_payment_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Payment ID cannot be empty')
        return v.strip()

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
            valid_transitions = PaymentStatus.get_valid_transitions(current_status)
            if v not in valid_transitions:
                raise ValueError(
                    f"Invalid status transition from {current_status} to {v}. "
                    f"Valid transitions: {[t.value for t in valid_transitions]}"
                )
        return v

    def is_terminal(self) -> bool:
        """Check if payment is in a terminal state"""
        return self.status in [PaymentStatus.FAILED, PaymentStatus.REFUNDED, PaymentStatus.CANCELLED]

    def can_be_retried(self) -> bool:
        """Check if payment can be retried"""
        return self.status == PaymentStatus.FAILED

    def can_be_refunded(self) -> bool:
        """Check if payment can be refunded"""
        return self.status == PaymentStatus.COMPLETED

    def is_successful(self) -> bool:
        """Check if payment was successful"""
        return self.status == PaymentStatus.COMPLETED

    def get_processing_time(self) -> Optional[float]:
        """Get payment processing time in seconds"""
        if self.processed_at and self.created_at:
            return (self.processed_at - self.created_at).total_seconds()
        return None