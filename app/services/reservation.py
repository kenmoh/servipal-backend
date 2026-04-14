# ───────────────────────────────────────────────
# Payment Initiation (Pay First)
# ───────────────────────────────────────────────
from decimal import Decimal
from uuid import UUID
import uuid

from fastapi import HTTPException, status
from supabase import AsyncClient

from app.schemas.common import PaymentCustomerInfo, PaymentCustomization, PaymentInitializationResponse
from app.schemas.reservation import CreateBooking
from app.utils.redis_utils import save_pending
from app.config.config import settings


async def initiate_reservation_payment(
    data: CreateBooking,
    customer_id: UUID,
    customer_info: dict,
    supabase: AsyncClient,
) -> dict:
    """
 
    """
    try:
        # Validate vendor
        vendor = (
            await supabase.table("reservation_settings")
            .select(
                "id, deposit_required, "
            )
            .eq("id", str(data.vendor_id))
            .eq("user_type", "RESTAURANT_VENDOR")
            .single()
            .execute()
        )

        if vendor["deposit_required"] != data.deposit_required:
            raise HTTPException(status_code=status.HTTP_406_NOT_ACCEPTABLE, detail=f'Invalid amount!  Expected {vendor['deposit_required']} got {data.deposit_required}')
            

        # Generate tx_ref
        tx_ref = f"RESERVATION-{uuid.uuid4().hex[:32].upper()}"

        # Save pending in Redis
        pending_data = {
            "customer_id": str(customer_id),
            "vendor_id": str(data.vendor_id),
            "table_id": str(data.table_id),
            "reservation_time": data.reservation_time,
            "end_time": data.end_time,
            "party_size": data.party_size,
            "number_of_children": data.number_of_children,
            "number_of_adult": data.number_of_adult,
            "deposit_required": f'{data.deposit_required}',
            "deposit_paid": f'{data.deposit_paid}',
            "business_name": data.business_name,
            "notes": data.notes or None
           
        }
        await save_pending(f"pending_reservation_{tx_ref}", pending_data, expire=1800)

        # Return SDK-ready data
        return PaymentInitializationResponse(
            tx_ref=tx_ref,
            amount=Decimal(str(data.deposit_required)),
            public_key=settings.FLUTTERWAVE_PUBLIC_KEY,
            currency="NGN",
            customer=PaymentCustomerInfo(
                email=customer_info.get("email"),
                phone_number=customer_info.get("phone_number"),
                full_name=customer_info.get("full_name") or "N/A",
            ),
            customization=PaymentCustomization(
                title="Servipal Reservations",
                description=f"{data.business_name} - Reservations",
                logo="https://mohdelivery.s3.us-east-1.amazonaws.com/favion/favicon.ico",
            ),
            message="Ready for payment",
        ).model_dump()

    except Exception as e:
        raise HTTPException(500, f"Reservation payment initialization failed: {str(e)}")