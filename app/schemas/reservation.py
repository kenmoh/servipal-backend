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
    deposit_required: int
    deposit_paid: int
    notes: str | None
    business_name: str
   