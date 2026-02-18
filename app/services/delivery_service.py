from fastapi import HTTPException, status, Request
from typing import Optional
import uuid
import datetime
from uuid import UUID
from decimal import Decimal
from fastapi import Request, HTTPException, status
from supabase import AsyncClient
from postgrest.exceptions import APIError
from app.schemas.delivery_schemas import (
    PackageDeliveryCreate,
    DeliveryStatus,
    DeliveryStatusUpdate,
)
from app.schemas.common import (
    PaymentInitializationResponse,
    PaymentCustomerInfo,
    PaymentCustomization,
)
from app.utils.redis_utils import save_pending
from app.config.config import settings
from app.config.logging import logger
from app.utils.audit import log_audit_event
from decimal import Decimal
from app.services.notification_service import notify_user
from decimal import Decimal


# ───────────────────────────────────────────────
# 1. Initiate Delivery (Pay First — No Rider Yet)
# ───────────────────────────────────────────────
async def initiate_delivery_payment(
    data: PackageDeliveryCreate,
    sender_id: UUID,
    supabase: AsyncClient,
    customer_info: dict,
) -> dict:
    """
    Step 1: Calculate delivery fee using DB charges
    Step 2: Generate tx_ref
    Step 3: Save pending state in Redis
    Step 4: Return data for Flutterwave RN SDK
    """
    logger.info("initiate_delivery_payment", sender_id=str(sender_id))

    try:
        # Get charges from DB
        charges = (
            await supabase.table("charges_and_commissions")
            .select("base_delivery_fee, delivery_fee_per_km, delivery_commission_rate")
            .single()
            .execute()
        )

        if not charges.data:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, "Charges configuration missing"
            )

        base_fee = Decimal(str(charges.data["base_delivery_fee"]))
        per_km_fee = Decimal(str(charges.data["delivery_fee_per_km"]))
        commission_rate = Decimal(str(charges.data["delivery_commission_rate"]))

        # Calculate delivery fee
        distance = Decimal(str(data.distance))
        delivery_fee = base_fee + (per_km_fee * distance)
        delivery_fee = round(delivery_fee, 2)

        # Generate tx_ref
        tx_ref = f"DELIVERY-{uuid.uuid4().hex[:32].upper()}"

        # Save to Redis (simpler now - no amount_due_dispatch needed!)
        pending_data = {
            "sender_id": str(sender_id),
            "delivery_data": data.model_dump(),
            "distance": str(distance),  # DB will recalculate from this
            "tx_ref": tx_ref,
            "created_at": datetime.datetime.now().isoformat(),
        }

        await save_pending(f"pending_delivery_{tx_ref}", pending_data, expire=1800)

        # Return for Flutterwave
        return PaymentInitializationResponse(
            tx_ref=tx_ref,
            amount=delivery_fee,
            public_key=settings.FLUTTERWAVE_PUBLIC_KEY,
            distance=str(distance),
            currency="NGN",
            receiver_phone=data.receiver_phone,
            pickup_location=data.pickup_location,
            destination=data.destination,
            package_name=data.package_name,
            duration=data.duration,
            customer=PaymentCustomerInfo(
                email=customer_info.get("email"),
                phone_number=customer_info.get("phone_number"),
                full_name=customer_info.get("full_name") or "N/A",
            ),
            customization=PaymentCustomization(
                title="Servipal Delivery",
                description=f"From {data.pickup_location} to {data.destination} ({distance} km)",
                logo="https://mohdelivery.s3.us-east-1.amazonaws.com/favion/favicon.ico",
            ),
            message="Ready for payment",
        ).model_dump()

    except Exception as e:
        logger.error("initiate_delivery_payment_error", error=str(e), exc_info=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Payment initiation failed: {str(e)}",
        )


# ============================================================
# MAIN ENTRY POINT - Routes to specific handlers
# ============================================================


async def update_delivery_status(
    tx_ref: str,
    data: DeliveryStatusUpdate,
    triggered_by_user_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """
    Main entry point for delivery status updates.
    Routes to appropriate handler based on status.
    """
    logger.info(
        "update_delivery_status_called",
        tx_ref=tx_ref,
        new_status=data.new_status.value,
        triggered_by=f'{triggered_by_user_id}',
    )

    try:
        # Fetch delivery for validation
        delivery = await _get_delivery(tx_ref, supabase)
        delivery_id = delivery["id"]

        # Validate authorization
        _validate_authorization(
            new_status=data.new_status,
            triggered_by_user_id=triggered_by_user_id,
            sender_id=delivery["sender_id"],
            rider_id=delivery["rider_id"] or None,
        )

        # Validate state transition
        _validate_state_transition(delivery["delivery_status"], data.new_status.value)

        # Route to specific handler
        if data.new_status == DeliveryStatus.ASSIGNED:
            result = await assign_rider(
                delivery_id, data.rider_id, triggered_by_user_id, supabase
            )

        elif data.new_status == DeliveryStatus.ACCEPTED:
            result = await accept_delivery(delivery_id, triggered_by_user_id, supabase)

        elif data.new_status == DeliveryStatus.PICKED_UP:
            result = await pickup_delivery(delivery_id, triggered_by_user_id, supabase)

        elif data.new_status == DeliveryStatus.IN_TRANSIT:
            result = await mark_in_transit(delivery_id, triggered_by_user_id, supabase)

        elif data.new_status == DeliveryStatus.DELIVERED:
            result = await mark_delivered(delivery_id, triggered_by_user_id, supabase)

        elif data.new_status == DeliveryStatus.COMPLETED:
            result = await complete_delivery(
                delivery_id, triggered_by_user_id, supabase, request
            )

        elif data.new_status == DeliveryStatus.CANCELLED:
            result = await cancel_delivery(
                delivery_id,
                triggered_by_user_id,
                data.cancellation_reason,
                supabase,
                request,
            )

        elif data.new_status == DeliveryStatus.DECLINED:
            result = await decline_delivery(delivery_id, supabase, request)

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {data.new_status.value}",
            )

        logger.info(
            "update_delivery_status_success",
            delivery_id=f'{delivery_id}',
            new_status=data.new_status.value,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "update_delivery_status_failed",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update delivery status: {str(e)}",
        )


# ============================================================
# HELPER: GET DELIVERY
# ============================================================


async def _get_delivery(tx_ref: str, supabase: AsyncClient) -> dict:
    """Fetch delivery details"""

    try:
        delivery_resp = (
            await supabase.table("delivery_orders")
            .select("id, sender_id, rider_id, delivery_status, order_number")
            .eq("tx_ref", tx_ref)
            .maybe_single()
            .execute()
        )

        if not delivery_resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found"
            )
        return delivery_resp.data
    except APIError as e:
        logger.error("fetch_delivery_error", error=str(e), errorr_message=f'{e.message}', exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error fetching delivery: {e.message}",
        )
        




# ============================================================
# 1. ASSIGN RIDER
# ============================================================


async def assign_rider(
    delivery_id: str,
    rider_id: str,
    sender_id: str,
    supabase: AsyncClient,
) -> dict:
    """
    Sender assigns a rider to delivery.
    - Validates rider availability
    - Updates status to ASSIGNED
    - Sets rider as busy
    - Sends notification to rider
    """
    if not rider_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="rider_id is required"
        )
    
    try:

    # Get tx_ref
        delivery = (
            await supabase.table("delivery_orders")
            .select("tx_ref, order_number")
            .eq("id", delivery_id)
            .single()
            .execute()
        )

        tx_ref = delivery.data["tx_ref"]
        order_number = delivery.data["order_number"]

        # Call RPC
        result = await supabase.rpc(
            "assign_rider_to_delivery",
            {
                "p_tx_ref": tx_ref,
                "p_rider_id": rider_id,
            },
        ).execute()

        if result.error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to assign rider: {result.error.message}",
            )

        result_data = result.data

        # Send notifications
        await _send_delivery_notifications(
            order_number=order_number,
            new_status=DeliveryStatus.ASSIGNED,
            sender_id=f'{sender_id}',
            rider_id=f'{rider_id}',
            dispatch_id=f'{result_data.get("dispatch_id")}',
            supabase=supabase,
        )

        return {
            "status": "success",
            "delivery_status": "ASSIGNED",
            "tx_ref": tx_ref,
            "rider_id": f'{rider_id}',
            "dispatch_id": f'{result_data.get("dispatch_id")}',
        }

    except APIError as e:
        logger.error("assign_rider_error", error=str(e), error_message=f'{e.message}', exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Something went wrong!",
        )


# ============================================================
# 2. ACCEPT DELIVERY
# ============================================================


async def accept_delivery(
    delivery_id: str,
    rider_id: str,
    supabase: AsyncClient,
) -> dict:
    """Rider accepts delivery - simple status update"""

    result = (
        await supabase.table("delivery_orders")
        .update(
            {
                "delivery_status": DeliveryStatus.ACCEPTED.value,
            }
        )
        .eq("id", delivery_id)
        .execute()
    )

    result_data = result.data[0]

    await _send_delivery_notifications(
        order_number=result_data["order_number"],
        new_status=DeliveryStatus.ACCEPTED,
        sender_id=result_data["sender_id"],
        rider_id=rider_id,
        dispatch_id=result_data.get("dispatch_id"),
        supabase=supabase,
    )

    return {
        "status": "success",
        "delivery_status": "ACCEPTED",
        "order_number": result_data["order_number"],
    }


# ============================================================
# 3. PICKUP DELIVERY (Money operation)
# ============================================================


async def pickup_delivery(
    delivery_id: str, rider_id: str, supabase: AsyncClient
) -> dict:
    """
    Rider picks up delivery.
    - Creates escrow holds
    - Starts tracking
    """
    result = await supabase.rpc(
        "mark_delivery_as_picked_up",
        {
            "p_delivery_id": delivery_id,
            "p_rider_id": rider_id,
        },
    ).execute()

    result_data = result.data

    await _send_delivery_notifications(
        order_number=result_data.get("order_number", ""),
        new_status=DeliveryStatus.PICKED_UP.value,
        sender_id=result_data["sender_id"],
        rider_id=rider_id,
        dispatch_id=result_data.get("dispatch_id"),
        supabase=supabase,
    )

    return result_data


# ============================================================
# 4. MARK IN TRANSIT
# ============================================================


async def mark_in_transit(
    delivery_id: str,
    rider_id: str,
    supabase: AsyncClient,
) -> dict:
    """Rider marks delivery as in transit"""
    result = (
        await supabase.table("delivery_orders")
        .update(
            {
                "delivery_status": DeliveryStatus.IN_TRANSIT.value,
            }
        )
        .eq("id", delivery_id)
        .execute()
    )

    result_data = result.data[0]

    await _send_delivery_notifications(
        order_number=result_data["order_number"],
        new_status=DeliveryStatus.IN_TRANSIT.value,
        sender_id=result_data["sender_id"],
        rider_id=rider_id,
        dispatch_id=result_data.get("dispatch_id"),
        supabase=supabase,
    )

    return {
        "status": "success",
        "delivery_status": "IN_TRANSIT",
        "order_number": result_data["order_number"],
    }


# ============================================================
# 5. MARK DELIVERED
# ============================================================


async def mark_delivered(
    delivery_id: str,
    rider_id: str,
    supabase: AsyncClient,
) -> dict:
    """Rider marks delivery as delivered"""
    result = (
        await supabase.table("delivery_orders")
        .update(
            {
                "delivery_status": DeliveryStatus.DELIVERED.value,
            }
        )
        .eq("id", delivery_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Delivery order not found"
        )

    result_data = result.data[0]

    await _send_delivery_notifications(
        order_number=result_data["order_number"],
        new_status=DeliveryStatus.DELIVERED,
        sender_id=result_data["sender_id"],
        rider_id=rider_id,
        dispatch_id=result_data.get("dispatch_id"),
        supabase=supabase,
    )

    return {
        "status": "success",
        "delivery_status": "DELIVERED",
        "order_number": result_data["order_number"],
    }


# ============================================================
# 6. COMPLETE DELIVERY (Money operation)
# ============================================================


async def complete_delivery(
    delivery_id: str,
    sender_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """
    Sender completes delivery.
    - Releases escrow
    - Pays dispatch
    - Frees up rider
    """
    result = await supabase.rpc(
        "mark_delivery_as_completed",
        {
            "p_delivery_id": delivery_id,
            "p_sender_id": sender_id,
        },
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Delivery order not found"
        )

    result_data = result.data

    await _send_delivery_notifications(
        order_number=result_data.get("order_number", ""),
        new_status=DeliveryStatus.COMPLETED,
        sender_id=sender_id,
        rider_id=result_data.get("rider_id"),
        dispatch_id=result_data["dispatch_id"],
        supabase=supabase,
    )

    await log_audit_event(
        supabase,
        entity_type="DELIVERY_ORDER",
        entity_id=delivery_id,
        action="COMPLETED",
        new_value={"status": "COMPLETED", "escrow": "RELEASED"},
        actor_id=sender_id,
        actor_type="USER",
        change_amount=Decimal(str(result_data["amount_released"])),
        notes="Delivery completed, escrow released",
        request=request,
    )

    return result_data


# ============================================================
# 7. CANCEL DELIVERY (Money operation)
# ============================================================


async def cancel_delivery(
    delivery_id: str,
    triggered_by_user_id: str,
    cancellation_reason: Optional[str],
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """
    Sender or Rider cancels delivery.
    - Handles refunds if escrow held
    - Handles returns if picked up
    """
    result = await supabase.rpc(
        "mark_delivery_as_cancelled",
        {
            "p_delivery_id": delivery_id,
            "p_triggered_by_user_id": triggered_by_user_id,
            "p_cancellation_reason": cancellation_reason,
        },
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Delivery order not found"
        )

    result_data = result.data

    await _send_delivery_notifications(
        order_number=result_data.get("order_number", ""),
        new_status=DeliveryStatus.CANCELLED,
        sender_id=result_data["sender_id"],
        rider_id=result_data.get("rider_id"),
        dispatch_id=result_data.get("dispatch_id"),
        cancellation_reason=cancellation_reason,
        cancelled_by_rider=result_data["cancelled_by"] == "RIDER",
        supabase=supabase,
    )

    await log_audit_event(
        supabase,
        entity_type="DELIVERY_ORDER",
        entity_id=delivery_id,
        action="CANCELLED",
        new_value={
            "status": "CANCELLED",
            "cancelled_by": result_data["cancelled_by"],
            "requires_return": result_data.get("requires_return", False),
        },
        actor_id=triggered_by_user_id,
        actor_type="USER",
        change_amount=Decimal(str(result_data["refund_amount"]))
        if result_data["refund_amount"] > 0
        else None,
        notes=result_data["message"],
        request=request,
    )

    return result_data


# ============================================================
# 8. DECLINE DELIVERY
# ============================================================


async def decline_delivery(
    delivery_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """Rider declines delivery assignment"""
    result = await supabase.rpc(
        "clear_rider_assignment",
        {
            "p_delivery_id": delivery_id,
        },
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Delivery order not found"
        )

    result_data = result.data

    await _send_delivery_notifications(
        order_number=result_data.get("order_number", ""),
        new_status=DeliveryStatus.DECLINED,
        sender_id=result_data.get("sender_id"),
        rider_id=None,
        dispatch_id=result_data.get("dispatch_id"),
        supabase=supabase,
    )

    await log_audit_event(
        supabase,
        entity_type="DELIVERY_ORDER",
        entity_id=delivery_id,
        action="DECLINED",
        new_value={"status": "PENDING", "rider_cleared": True},
        actor_id=None,
        actor_type="USER",
        notes="Rider declined assignment",
        request=request,
    )

    return result_data


# ============================================================
# REUSABLE VALIDATORS
# ============================================================

# ============================================================
# AUTHORIZATION VALIDATION
# ============================================================


def _validate_authorization(
    new_status: DeliveryStatus,
    triggered_by_user_id: str,
    sender_id: str,
    rider_id: Optional[str],
):
    """
    Validate that the user has permission to set this status.

    Authorization Matrix:
    - ASSIGNED: Sender only
    - ACCEPTED: Rider only
    - PICKED_UP: Rider only
    - IN_TRANSIT: Rider only
    - DELIVERED: Rider only
    - COMPLETED: Sender only
    - CANCELLED: Sender OR Rider
    - DECLINED: Rider only
    """

    if new_status == DeliveryStatus.ASSIGNED:
        if triggered_by_user_id != sender_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only sender can assign a rider",
            )

    elif new_status == DeliveryStatus.ACCEPTED:
        if not rider_id or triggered_by_user_id != rider_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assigned rider can accept delivery",
            )

    elif new_status in [
        DeliveryStatus.PICKED_UP,
        DeliveryStatus.IN_TRANSIT,
        DeliveryStatus.DELIVERED,
    ]:
        if not rider_id or triggered_by_user_id != rider_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only the assigned rider can set status to {new_status.value}",
            )

    elif new_status == DeliveryStatus.COMPLETED:
        if triggered_by_user_id != sender_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only sender can mark delivery as completed",
            )

    elif new_status == DeliveryStatus.CANCELLED:
        # Sender OR Rider can cancel
        if triggered_by_user_id not in [sender_id, rider_id]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only sender or rider can cancel delivery",
            )

    elif new_status == DeliveryStatus.DECLINED:
        if not rider_id or triggered_by_user_id != rider_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assigned rider can decline delivery",
            )


# ============================================================
# STATE TRANSITION VALIDATION (State Machine)
# ============================================================


def _validate_state_transition(current_status: str, new_status: str):
    """
    Validate that the status transition is allowed.

    State Machine:
    PENDING → ASSIGNED
    ASSIGNED → ACCEPTED | DECLINED
    ACCEPTED → PICKED_UP | CANCELLED
    PICKED_UP → IN_TRANSIT | DELIVERED | CANCELLED
    IN_TRANSIT → DELIVERED | CANCELLED
    DELIVERED → COMPLETED | CANCELLED

    Terminal states: COMPLETED, CANCELLED (cannot transition from these)
    """

    # Define allowed transitions
    ALLOWED_TRANSITIONS = {
        "PENDING": ["ASSIGNED", "CANCELLED"],
        "ASSIGNED": ["ACCEPTED", "DECLINED", "CANCELLED"],
        "DECLINED": ["ASSIGNED"],  # Can reassign after decline
        "ACCEPTED": ["PICKED_UP", "CANCELLED"],
        "PICKED_UP": ["IN_TRANSIT", "DELIVERED", "CANCELLED"],
        "IN_TRANSIT": ["DELIVERED", "CANCELLED"],
        "DELIVERED": ["COMPLETED", "CANCELLED"],
        "COMPLETED": [],  # Terminal state
        "CANCELLED": [],  # Terminal state
    }

    allowed = ALLOWED_TRANSITIONS.get(current_status, [])

    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from {current_status} to {new_status}. Allowed transitions: {', '.join(allowed) if allowed else 'None (terminal state)'}",
        )


async def _send_delivery_notifications(
    order_number: str,
    new_status: DeliveryStatus,
    sender_id: str,
    rider_id: Optional[str],
    dispatch_id: Optional[str],
    cancellation_reason: Optional[str] = None,
    decline_reason: Optional[str] = None,
    cancelled_by_rider: bool = False,
    supabase: AsyncClient = None,
):
    """Send notifications to relevant parties based on delivery status."""

    notification_config = {
        DeliveryStatus.ASSIGNED: {
            "rider": {
                "title": "New Delivery Assignment",
                "message": "You have been assigned a new delivery. Please review and accept.",
                "data": {"type": "DELIVERY_ASSIGNED", "order_number": order_number},
            }
        },
        DeliveryStatus.ACCEPTED: {
            "sender": {
                "title": "Delivery Accepted",
                "message": "Rider has accepted your delivery request and will pick up soon.",
                "data": {"type": "DELIVERY_ACCEPTED", "order_number": order_number},
            },
            "dispatch": {
                "title": "Delivery Accepted",
                "message": "Rider has accepted the delivery request.",
                "data": {"type": "DELIVERY_ACCEPTED", "order_number": order_number},
            },
        },
        DeliveryStatus.DECLINED: {
            "sender": {
                "title": "Pickup Declined",
                "message": f"Rider declined the pickup. Reason: {decline_reason or 'Not provided'}. Please assign another rider.",
                "data": {
                    "type": "DELIVERY_DECLINED",
                    "order_number": order_number,
                    "reason": decline_reason,
                },
            },
            "dispatch": {
                "title": "Pickup Declined",
                "message": f"Rider declined the pickup. Please reassign.",
                "data": {
                    "type": "DELIVERY_DECLINED",
                    "order_number": order_number,
                    "reason": decline_reason,
                },
            },
        },
        DeliveryStatus.PICKED_UP: {
            "sender": {
                "title": "Package Picked Up",
                "message": "Rider has picked up your package and is preparing for delivery.",
                "data": {"type": "DELIVERY_PICKED_UP", "order_number": order_number},
            },
            "dispatch": {
                "title": "Package Picked Up",
                "message": "Rider has picked up the package.",
                "data": {"type": "DELIVERY_PICKED_UP", "order_number": order_number},
            },
        },
        DeliveryStatus.IN_TRANSIT: {
            "sender": {
                "title": "Package In Transit",
                "message": "Your package is now in transit to the destination.",
                "data": {"type": "DELIVERY_IN_TRANSIT", "order_number": order_number},
            },
            "dispatch": {
                "title": "Package In Transit",
                "message": "Package is in transit.",
                "data": {"type": "DELIVERY_IN_TRANSIT", "order_number": order_number},
            },
        },
        DeliveryStatus.DELIVERED: {
            "sender": {
                "title": "Package Delivered",
                "message": "Your package has been delivered. Please confirm receipt.",
                "data": {"type": "DELIVERY_DELIVERED", "order_number": order_number},
            },
            "dispatch": {
                "title": "Package Delivered",
                "message": "Package has been delivered successfully.",
                "data": {"type": "DELIVERY_DELIVERED", "order_number": order_number},
            },
        },
        DeliveryStatus.COMPLETED: {
            "rider": {
                "title": "Delivery Completed",
                "message": "Sender has confirmed receipt. Payment has been processed.",
                "data": {"type": "DELIVERY_COMPLETED", "order_number": order_number},
            },
            "dispatch": {
                "title": "Delivery Completed",
                "message": "Delivery has been completed and confirmed.",
                "data": {"type": "DELIVERY_COMPLETED", "order_number": order_number},
            },
        },
        DeliveryStatus.CANCELLED: {
            # Different messages based on who cancelled
        },
    }

    # Handle CANCELLED status separately (different messages based on who cancelled)
    if new_status == DeliveryStatus.CANCELLED:
        if cancelled_by_rider:
            # Notify sender and dispatch
            await notify_user(
                sender_id,
                "Delivery Cancelled by Rider",
                f"Rider has cancelled the delivery. Reason: {cancellation_reason or 'Not provided'}. You have been refunded.",
                data={
                    "type": "DELIVERY_CANCELLED_BY_RIDER",
                    "order_number": order_number,
                    "reason": cancellation_reason,
                },
                supabase=supabase,
            )

            if dispatch_id:
                await notify_user(
                    dispatch_id,
                    "Delivery Cancelled by Rider",
                    f"Rider has cancelled the delivery. Please reassign.",
                    data={
                        "type": "DELIVERY_CANCELLED_BY_RIDER",
                        "order_number": order_number,
                        "reason": cancellation_reason,
                    },
                    supabase=supabase,
                )
        else:
            # Cancelled by sender - notify rider and dispatch
            if rider_id:
                await notify_user(
                    rider_id,
                    "Delivery Cancelled by Sender",
                    f"Sender has cancelled the delivery. Reason: {cancellation_reason or 'Not provided'}.",
                    data={
                        "type": "DELIVERY_CANCELLED_BY_SENDER",
                        "order_number": order_number,
                        "reason": cancellation_reason,
                    },
                    supabase=supabase,
                )

            if dispatch_id:
                await notify_user(
                    dispatch_id,
                    "Delivery Cancelled",
                    f"Sender has cancelled the delivery.",
                    data={
                        "type": "DELIVERY_CANCELLED_BY_SENDER",
                        "order_number": order_number,
                        "reason": cancellation_reason,
                    },
                    supabase=supabase,
                )

    else:
        # Send notifications based on config
        config = notification_config.get(new_status, {})

        # Notify sender
        if "sender" in config and sender_id:
            notif = config["sender"]
            await notify_user(
                sender_id,
                notif["title"],
                notif["message"],
                data=notif["data"],
                supabase=supabase,
            )

        # Notify rider
        if "rider" in config and rider_id:
            notif = config["rider"]
            await notify_user(
                rider_id,
                notif["title"],
                notif["message"],
                data=notif["data"],
                supabase=supabase,
            )

        # Notify dispatch
        if "dispatch" in config and dispatch_id:
            notif = config["dispatch"]
            await notify_user(
                dispatch_id,
                notif["title"],
                notif["message"],
                data=notif["data"],
                supabase=supabase,
            )
