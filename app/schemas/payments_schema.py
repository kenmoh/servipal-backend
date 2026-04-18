from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime
from uuid import uuid4


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


class InitiatePreauthRequest(BaseModel):
    # Card details (sent encrypted to Flutterwave)
    card_number: str
    expiry_month: str
    expiry_year: str
    cvv: str

    # Transaction details
    currency: str = "NGN"
    amount: str
    email: str
    fullname: str
    phone_number: str
    redirect_url: Optional[str] = None

    # Flutterwave flags
    usesecureauth: bool = False

    # Your reference for idempotency/tracking
    tx_ref: str = ""

    def model_post_init(self, __context):
        if not self.tx_ref:
            self.tx_ref = f"PREAUTH-{uuid4().hex}"


class PreauthCaptureRequest(BaseModel):
    amount: str


class PreauthRefundRequest(BaseModel):
    amount: str
