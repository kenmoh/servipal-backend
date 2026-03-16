from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel


class ChargesBase(BaseModel):
    payment_gateway_fee: Decimal = Decimal("0.00")
    value_added_tax: Decimal = Decimal("0.00")
    payout_charge_upto_5000: Decimal = Decimal("0.00")
    payout_charge_5001_to_50000: Decimal = Decimal("0.00")
    payout_charge_above_50000: Decimal = Decimal("0.00")
    stamp_duty: Decimal = Decimal("0.00")
    base_delivery_fee: Decimal = Decimal("0.00")
    delivery_fee_per_km: Decimal = Decimal("0.00")
    delivery_commission_percentage: Decimal = Decimal("0.00")
    food_commission_percentage: Decimal = Decimal("0.00")
    laundry_commission_percentage: Decimal = Decimal("0.00")
    product_commission_percentage: Decimal = Decimal("0.00")
    delivery_commission_rate: Decimal = Decimal("0.00")
    food_commission_rate: Decimal = Decimal("0.00")
    laundry_commission_rate: Decimal = Decimal("0.00")
    product_commission_rate: Decimal = Decimal("0.00")


class ChargesCreate(ChargesBase):
    pass


class ChargesUpdate(ChargesBase):
    pass  


class ChargesResponse(ChargesBase):
    id: UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}