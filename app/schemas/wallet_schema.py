from pydantic import BaseModel, Field
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum


class WalletTransactionResponse(BaseModel):
    tx_ref: str
    amount: Decimal = Field(max_digits=6, decimal_places=2, default=0.00)
    from_user_id: Optional[UUID]
    to_user_id: Optional[UUID]
    order_id: Optional[UUID]
    transaction_type: str
    status: str
    payment_method: str
    created_at: datetime


class WalletBalanceResponse(BaseModel):
    balance: Decimal = Field(max_digits=6, decimal_places=2, default=0.00)
    escrow_balance: Decimal = Field(max_digits=6, decimal_places=2, default=0.00)
    transactions: List[WalletTransactionResponse]


class TopUpResponse(BaseModel):
    tx_ref: str
    amount: Decimal = Field(max_digits=6, decimal_places=2, default=0.00)


class TopUpRequest(BaseModel):
    amount: Decimal = Field(
        ..., description="Amount to be charged (in NGN)", min=1000, max=25_000
    )


class PayWithWalletRequest(BaseModel):
    amount: Decimal
    to_user_id: Optional[UUID]
    order_id: Optional[UUID]
    transaction_type: str = "ORDER_PAYMENT"
    details: Optional[Dict] = None


class CustomerInfo(BaseModel):
    email: str = Field(..., description="Customer's email address")
    # phone_number: str = Field(..., description="Customer's phone number (E.164 format)")
    name: str = Field(..., description="Customer's full name or display name")


class Customization(BaseModel):
    title: str = Field(..., description="Title shown on the payment page/SDK")
    description: str = Field(
        ..., description="Description shown on the payment page/SDK"
    )


class WalletTopUpInitiationResponse(BaseModel):
    """
    Response schema for initiating a wallet top-up.
    Returned when user requests to add funds to their wallet.
    """

    tx_ref: str = Field(..., description="Unique transaction reference for this top-up")
    amount: float = Field(..., description="Amount to be charged (in NGN)")
    public_key: str = Field(
        ..., description="Flutterwave public key for SDK initialization"
    )
    currency: str = Field("NGN", description="Currency code (always NGN for now)")
    customer: CustomerInfo = Field(
        ..., description="Customer details for Flutterwave SDK"
    )
    customization: Customization = Field(
        ..., description="UI customizations for the payment screen"
    )


class PayWithWalletResponse(BaseModel):
    success: bool = Field(..., description="Payment successful from wallet")
    message: str = Field(..., description="Payment successful from wallet")
    new_balance: Decimal = Field(..., description="New balance after payment")
    tx_ref: str = Field(..., description="Unique transaction reference for this top-up")


class WithdrawAllRequest(BaseModel):
    bank_name: str = Field(..., min_length=2)
    account_number: str = Field(..., min_length=10, max_length=10)
    account_name: str = Field(..., min_length=2)
    narration: Optional[str] = Field(
        "Servipal Wallet Withdrawal", description="Optional reference"
    )


class WithdrawResponse(BaseModel):
    success: bool
    message: str
    amount_withdrawn: Decimal
    fee: Decimal
    net_amount: Decimal
    transaction_id: str
    flutterwave_ref: Optional[str]
    status: str


class WithdrawalCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    bank_name: str
    account_number: str
    account_name: str


class WithdrawalResponse(BaseModel):
    id: UUID
    user_id: UUID
    amount: Decimal
    fee: Decimal
    bank_name: str
    account_number: str
    account_name: str
    status: str
    created_at: datetime
    approved_at: Optional[datetime] = None
    flutterwave_ref: Optional[str] = None


class WithdrawalListResponse(BaseModel):
    withdrawals: List[WithdrawalResponse]
    total_count: int


class TransactionType(str, Enum):
    TOP_UP = "TOP_UP"
    PRODUCT_ORDER = "PRODUCT_ORDER"
    FOOD_ORDER = "FOOD_ORDER"
    LAUNDRY_ORDER = "LAUNDRY_ORDER"
    DELIVERY_FEE = "DELIVERY_FEE"
    WITHDRAWAL = "WITHDRAWAL"
