from fastapi import APIRouter, Depends
from supabase import AsyncClient

from app.database.supabase import get_supabase_client
from app.dependencies.auth import get_current_profile, get_customer_contact_info
from app.schemas.reservation import CreateBooking
from app.services import reservation


router = APIRouter(prefix="/api/v1/reservations", tags=["Reservations"])


@router.post("/initiate-payment")
async def initiate_reservation_payment_endpoint(
    data: CreateBooking,
    current_profile: dict = Depends(get_current_profile),
    customer_info: dict = Depends(get_customer_contact_info),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    """
    Initiate laundry payments.

    Args:
        data (CreateBooking): Order details.

    Returns:
        dict: Flutterwave RN SDK payments data.
    """
    return await reservation.initiate_reservation_payment(
        data, current_profile["id"], customer_info, supabase
    )
