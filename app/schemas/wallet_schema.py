from pydantic import BaseModel, Field, UUID4
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, List, Any
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
    amount: Decimal = Field(..., description="Amount to be charged (in NGN)")
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
    status: str = Field(..., description="Status of the payment")
    order_id: UUID = Field(..., description="The order ID associated with the payment")
    tx_ref: str = Field(..., description="Unique transaction reference for this top-up")
    grand_total: Decimal = Field(..., description="Total amount of the payment")
    message: str = Field(..., description="Payment successful from wallet")


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


class OrderType(str, Enum):
    FOOD = "FOOD"
    PRODUCT = "PRODUCT"
    LAUNDRY = "LAUNDRY"
    DELIVERY = "DELIVERY"


class PaymentWithWalletData(BaseModel):
    amount: Decimal
    tx_ref: str


class WalletPaymentRequest(BaseModel):
    order_type: OrderType

    # Shared
    # grand_total: Decimal
    additional_info: Optional[str] = None

    # FOOD / LAUNDRY / PRODUCT shared
    vendor_id: Optional[UUID4] = None
    delivery_fee: Optional[Decimal] = None
    delivery_option: Optional[str] = None
    order_data: Optional[List[Any]] = None
    destination: Optional[str] = None

    # FOOD specific
    # total_price: Optional[Decimal] = None

    # LAUNDRY specific
    # subtotal: Optional[Decimal] = None

    # PRODUCT specific
    product_id: Optional[UUID4] = None
    quantity: Optional[int] = None
    product_name: Optional[str] = None
    price: Optional[Decimal] = None
    shipping_cost: Optional[float] = None
    delivery_address: Optional[str] = None
    images: Optional[List[Any]] = None
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None

    # DELIVERY specific
    distance: Optional[Decimal] = None
    package_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    sender_phone_number: Optional[str] = None
    pickup_location: Optional[str] = None
    pickup_coordinates: Optional[str] = None
    dropoff_coordinates: Optional[str] = None
    delivery_type: Optional[str] = None
    duration: Optional[str] = None
    package_image_url: Optional[str] = None
