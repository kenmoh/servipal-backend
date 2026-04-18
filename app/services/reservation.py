# ───────────────────────────────────────────────
# Payment Initiation (Pay First)
# ───────────────────────────────────────────────
from decimal import Decimal
from uuid import UUID
import uuid

from fastapi import HTTPException, status
from supabase import AsyncClient

from app.schemas.common import (
    PaymentCustomerInfo,
    PaymentCustomization,
    PaymentInitializationResponse,
)
from app.schemas.reservation import CreateBooking
from app.utils.redis_utils import save_pending
from app.config.config import settings
from app.config.logging import logger


async def initiate_reservation_payment(
    data: CreateBooking,
    customer_id: UUID,
    customer_info: dict,
    supabase: AsyncClient,
) -> dict:
    try:
        #  Validate vendor settings
        vendor = (
            await supabase.table("reservation_settings")
            .select("vendor_id, min_deposit_adult")
            .eq("vendor_id", str(data.vendor_id))
            .single()
            .execute()
        )

        if not vendor.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor not found",
            )

        if vendor.data["min_deposit_adult"] != data.deposit_required:
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail=f"Invalid amount! Expected {vendor.data['min_deposit_adult']} got {data.deposit_required}",
            )

        # Generate idempotency key
        tx_ref = f"RESERVATION-{uuid.uuid4().hex[:32].upper()}"

        #  Create reservation intent (source of truth)
        reservation_intent = await supabase.rpc(
            "create_reservation_intent",
            {
                "p_vendor_id": str(data.vendor_id),
                "p_customer_id": str(customer_id),
                "p_reservation_date": data.reservation_date,
                "p_reservation_time": data.reservation_time,
                "p_serving_period": data.serving_period,
                "p_party_size": data.party_size,
                "p_number_of_adults": data.number_of_adults,
                "p_number_of_children": data.number_of_children,
                "p_tx_ref": tx_ref,
                "p_metadata": {
                    "notes": data.notes or None,
                    "business_name": data.business_name,
                },
            },
        ).execute()

        if not reservation_intent.data:
            raise HTTPException(500, "Failed to create reservation intent")
        
        amount = reservation_intent.data["total_deposit"]
        tx_ref = reservation_intent.data["tx_ref"]
        
        # # Save pending in Redis
        # pending_data = {
        #     "customer_id": str(customer_id),
        #     "vendor_id": str(data.vendor_id),
        #     "table_id": str(data.table_id),
        #     "reservation_time": data.reservation_time,
        #     "end_time": data.end_time,
        #     "party_size": data.party_size,
        #     "number_of_children": data.number_of_children,
        #     "number_of_adult": data.number_of_adult,
        #     "deposit_required": f"{data.deposit_required}",
        #     "deposit_paid": f"{data.deposit_paid}",
        #     "business_name": data.business_name,
        #     "notes": data.notes or None,
        # }
        # await save_pending(f"pending_reservation_{tx_ref}", pending_data, expire=1800)

        # log
        logger.info(
            "reservation_payment_initiated",
            tx_ref=tx_ref,
            customer_id=str(customer_id),
            vendor_id=str(data.vendor_id),
        )

        #  return payment payload
        return PaymentInitializationResponse(
            tx_ref=tx_ref,
            amount=Decimal(str(amount)),
            public_key=settings.FLUTTERWAVE_PUBLIC_KEY,
            currency="NGN",
            customer=PaymentCustomerInfo(
                email=customer_info.get("email"),
                phone_number=customer_info.get("phone_number"),
                full_name=customer_info.get("full_name") or "N/A",
            ),
            customization=PaymentCustomization(
                title="ServiPal Reservations",
                description=f"{data.business_name} - Reservations",
                logo="https://mohdelivery.s3.us-east-1.amazonaws.com/favion/favicon.ico",
            ),
            message="Ready for payment",
        ).model_dump()

    except Exception as e:
        logger.error("reservation_payment_failed", error=str(e))
        raise HTTPException(500, f"Payment initialization failed: {str(e)}")
