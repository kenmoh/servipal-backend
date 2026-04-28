from decimal import Decimal

from pydantic import BaseModel


class CreateBooking(BaseModel):
    vendor_id: str
    customer_id: str
    reservation_time: str
    reservation_date: str
    serving_period: str
    party_size: int
    number_of_children: int
    number_of_adults: int
    min_deposit_adult: Decimal
    notes: str | None
    business_name: str
    day_of_week: str
