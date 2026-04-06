from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime


class MarkPaymentSuccessRequest(BaseModel):
    order_id: UUID4
    flutterwave_tx_id: str
    scheduled_payout_at: datetime


class PaymentResponse(BaseModel):
    id: UUID4
    order_id: UUID4
    payment_status: str
    payout_status: str
    total_amount: float
    vendor_amount: float
    created_at: datetime


class ProcessPayoutRequest(BaseModel):
    order_payment_id: UUID4
    flutterwave_transfer_id: str
    flutterwave_reference: str


class PayoutResponse(BaseModel):
    id: UUID4
    vendor_id: UUID4
    amount: float
    status: str

class CreateRefundRequest(BaseModel):
    order_payment_id: UUID4
    amount: float
    reason: Optional[str] = None


class RefundResponse(BaseModel):
    id: UUID4
    amount: float
    status: str