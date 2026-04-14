from pydantic import BaseModel


class CreateBooking(BaseModel):
    vendor_id: str
    table_id: str
    reservation_time: str
    end_time: str
    party_size: int
    number_of_children: int
    number_of_adult: int
    deposit_required: int
    deposit_paid: int
    notes: str | None
    business_name: str