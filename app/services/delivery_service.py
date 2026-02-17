from fastapi import HTTPException, status, Request
from typing import Optional
import uuid
from uuid import UUID
import datetime


from typing import Optional
from uuid import UUID
from decimal import Decimal
from fastapi import Request, HTTPException, status
from supabase import AsyncClient
from app.utils.audit import log_audit_event
from app.config.logging import logger

from app.schemas.delivery_schemas import (
    PackageDeliveryCreate,
    DeliveryStatus,
    DeliveryStatusUpdate,
    AssignRiderRequest,
    AssignRiderResponse,
    DeliveryCancelRequest,
    DeliveryCancelResponse,
    DeliveryAction,
    DeliveryActionResponse,
    DeliveryOrdersResponse,
    DeliveryOrderListItem,
)
from app.schemas.common import (
    PaymentInitializationResponse,
    PaymentCustomerInfo,
    PaymentCustomization,
)
from supabase import AsyncClient
from app.utils.redis_utils import save_pending
from app.utils.commission import get_commission_rate
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
                status.HTTP_500_INTERNAL_SERVER_ERROR, 
                "Charges configuration missing"
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
        triggered_by=triggered_by_user_id,
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
            rider_id=delivery["rider_id"] or None
        )
        
        # Validate state transition
        _validate_state_transition(delivery["delivery_status"], data.new_status.value)
        
        # Route to specific handler
        if data.new_status == DeliveryStatus.ASSIGNED:
            result = await assign_rider(delivery_id, data.rider_id, triggered_by_user_id, supabase, request)
            
        elif data.new_status == DeliveryStatus.ACCEPTED:
            result = await accept_delivery(delivery_id, triggered_by_user_id, supabase)
            
        elif data.new_status == DeliveryStatus.PICKED_UP:
            result = await pickup_delivery(delivery_id, triggered_by_user_id, supabase, request)
            
        elif data.new_status == DeliveryStatus.IN_TRANSIT:
            result = await mark_in_transit(delivery_id, triggered_by_user_id, supabase, request)
            
        elif data.new_status == DeliveryStatus.DELIVERED:
            result = await mark_delivered(delivery_id, triggered_by_user_id, supabase, request)
            
        elif data.new_status == DeliveryStatus.COMPLETED:
            result = await complete_delivery(delivery_id, triggered_by_user_id, supabase, request)
            
        elif data.new_status == DeliveryStatus.CANCELLED:
            result = await cancel_delivery(delivery_id, triggered_by_user_id, data.cancellation_reason, supabase, request)
            
        elif data.new_status == DeliveryStatus.DECLINED:
            result = await decline_delivery(delivery_id, supabase, request)
            
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {data.new_status.value}"
            )
        
        logger.info(
            "update_delivery_status_success",
            delivery_id=delivery_id,
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
            detail=f"Failed to update delivery status: {str(e)}"
        )


# ============================================================
# HELPER: GET DELIVERY
# ============================================================

async def _get_delivery(tx_ref: str, supabase: AsyncClient) -> dict:
    """Fetch delivery details"""
    delivery_resp = await supabase.table("delivery_orders").select(
        "id, sender_id, rider_id, delivery_status, order_number"
    ).eq("tx_ref", tx_ref).maybe_single().execute()
    
    if not delivery_resp.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found"
        )

    logger.error('***************************************************************')

     
    logger.info(
        "update_delivery_status_success",
        data=delivery_resp.data,
       
    )

    logger.error('***************************************************************')
    
    return delivery_resp.data


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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rider_id is required"
        )
    
    # Get tx_ref
    delivery = await supabase.table("delivery_orders").select(
        "tx_ref, order_number"
    ).eq("id", delivery_id).single().execute()
    
    tx_ref = delivery.data["tx_ref"]
    order_number = delivery.data["order_number"]
    
    # Update delivery with rider_id first
    # await supabase.table("delivery_orders").update({
    #     "rider_id": rider_id
    # }).eq("id", delivery_id).execute()
    
    # Call RPC
    result = await supabase.rpc("assign_rider_to_delivery", {
        "p_tx_ref": tx_ref,
        "p_rider_id": rider_id,
    }).execute()
    
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign rider: {result.error.message}"
        )
    
    result_data = result.data
    
    # Send notifications
    await _send_delivery_notifications(
        order_number=order_number,
        new_status=DeliveryStatus.ASSIGNED,
        sender_id=sender_id,
        rider_id=rider_id,
        dispatch_id=result_data.get("dispatch_id"),
        supabase=supabase,
    )
    
    # Audit log
    # await log_audit_event(
    #     supabase,
    #     entity_type="DELIVERY_ORDER",
    #     entity_id=delivery_id,
    #     action="RIDER_ASSIGNED",
    #     new_value={"status": "ASSIGNED", "rider_id": rider_id},
    #     actor_id=sender_id,
    #     actor_type="USER",
    #     notes=f"Rider assigned to delivery",
    #     request=request,
    # )
    
    return {
        "status": "success",
        "delivery_status": "ASSIGNED",
        "tx_ref": tx_ref,
        "rider_id": rider_id,
        "dispatch_id": result_data.get("dispatch_id"),
    }


# ============================================================
# 2. ACCEPT DELIVERY
# ============================================================

async def accept_delivery(
    delivery_id: str,
    rider_id: str,
    supabase: AsyncClient,
) -> dict:
    """Rider accepts delivery - simple status update"""
    
    result = await supabase.table("delivery_orders").update({
        "delivery_status": DeliveryStatus.ACCEPTED.value,
    }).eq("id", delivery_id).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update delivery status"
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
    delivery_id: str,
    rider_id: str,
    supabase: AsyncClient
) -> dict:
    """
    Rider picks up delivery.
    - Creates escrow holds
    - Starts tracking
    """
    result = await supabase.rpc("mark_delivery_as_picked_up", {
        "p_delivery_id": delivery_id,
        "p_rider_id": rider_id,
    }).execute()
    
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error.message
        )
    
    result_data = result.data
    
    await _send_delivery_notifications(
        order_number=result_data.get("order_number", ""),
        new_status=DeliveryStatus.PICKED_UP.value,
        sender_id=result_data["sender_id"],
        rider_id=rider_id,
        dispatch_id=result_data.get("dispatch_id"),
        supabase=supabase,
    )
    
    # await log_audit_event(
    #     supabase,
    #     entity_type="DELIVERY_ORDER",
    #     entity_id=delivery_id,
    #     action="PICKED_UP",
    #     new_value={"status": "PICKED_UP", "escrow": "HELD"},
    #     actor_id=rider_id,
    #     actor_type="USER",
    #     change_amount=Decimal(str(result_data["escrow_amount"])),
    #     notes="Delivery picked up, escrow held",
    #     request=request,
    # )
    
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
    result = await supabase.table("delivery_orders").update({
        "delivery_status": DeliveryStatus.IN_TRANSIT.value,
    }).eq("id", delivery_id).execute()

    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error.message
        )
    
    result_data = result.data
    
    await _send_delivery_notifications(
        order_number=result_data["order_number"],
        new_status=DeliveryStatus.IN_TRANSIT.value,
        sender_id=result_data["sender_id"],
        rider_id=rider_id,
        dispatch_id=result_data.get("dispatch_id"),
        supabase=supabase,
    )
    
    # await log_audit_event(
    #     supabase,
    #     entity_type="DELIVERY_ORDER",
    #     entity_id=delivery_id,
    #     action="IN_TRANSIT",
    #     new_value={"status": "IN_TRANSIT"},
    #     actor_id=rider_id,
    #     actor_type="USER",
    #     notes="Delivery in transit",
    #     request=request,
    # )
    
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
    result = await supabase.table("delivery_orders").update({
        "delivery_status": DeliveryStatus.DELIVERED.value,
    }).eq("id", delivery_id).execute()
    
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error.message
        )
    
    result_data = result.data
    
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
    result = await supabase.rpc("mark_delivery_as_completed", {
        "p_delivery_id": delivery_id,
        "p_sender_id": sender_id,
    }).execute()
    
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error.message
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
    result = await supabase.rpc("mark_delivery_as_cancelled", {
        "p_delivery_id": delivery_id,
        "p_triggered_by_user_id": triggered_by_user_id,
        "p_cancellation_reason": cancellation_reason,
    }).execute()
    
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error.message
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
        change_amount=Decimal(str(result_data["refund_amount"])) if result_data["refund_amount"] > 0 else None,
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
    result = await supabase.rpc("clear_rider_assignment", {
        "p_delivery_id": delivery_id,
    }).execute()
    
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error.message
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
    rider_id: Optional[str]
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
                detail="Only sender can assign a rider"
            )
    
    elif new_status == DeliveryStatus.ACCEPTED:
        if not rider_id or triggered_by_user_id != rider_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assigned rider can accept delivery"
            )
    
    elif new_status in [DeliveryStatus.PICKED_UP, DeliveryStatus.IN_TRANSIT, DeliveryStatus.DELIVERED]:
        if not rider_id or triggered_by_user_id != rider_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only the assigned rider can set status to {new_status.value}"
            )
    
    elif new_status == DeliveryStatus.COMPLETED:
        if triggered_by_user_id != sender_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only sender can mark delivery as completed"
            )
    
    elif new_status == DeliveryStatus.CANCELLED:
        # Sender OR Rider can cancel
        if triggered_by_user_id not in [sender_id, rider_id]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only sender or rider can cancel delivery"
            )
    
    elif new_status == DeliveryStatus.DECLINED:
        if not rider_id or triggered_by_user_id != rider_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the assigned rider can decline delivery"
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
            detail=f"Cannot transition from {current_status} to {new_status}. Allowed transitions: {', '.join(allowed) if allowed else 'None (terminal state)'}"
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



# async def pickup_delivery(
#     delivery_id: str,
#     rider_id: str,
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ) -> dict:
#     """
#     Rider picks up delivery.
#     - Moves sender balance → sender escrow
#     - Holds dispatch escrow
#     - Creates 2 ESCROW_HOLD transactions (DEBIT + CREDIT)
#     """
#     logger.info(
#         "pickup_delivery_called",
#         delivery_id=delivery_id,
#         rider_id=rider_id,
#     )

#     try:
#         # Call atomic RPC
#         result = await supabase.rpc("mark_delivery_as_picked_up", {
#             "p_delivery_id": delivery_id,
#             "p_rider_id": rider_id,
#         }).execute()

#         result_data = result.data

#         if result.error:
#             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, result.error.message)

#         # Notify sender
#         await notify_user(
#             user_id=result_data["sender_id"],
#             title="Delivery Picked Up",
#             body="Your delivery has been picked up by the rider",
#             data={
#                 "delivery_id": delivery_id,
#                 "type": "DELIVERY_PICKED_UP",
#                 "rider_id": rider_id,
#             },
#             supabase=supabase,
#         )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type="DELIVERY_ORDER",
#             entity_id=delivery_id,
#             action="PICKED_UP",
#             new_value={"status": "PICKED_UP", "escrow": "HELD"},
#             actor_id=rider_id,
#             actor_type="USER",
#             change_amount=Decimal(str(result_data["escrow_amount"])),
#             notes="Delivery picked up by rider, escrow held",
#             request=request,
#         )

#         logger.info(
#             "pickup_delivery_success",
#             delivery_id=delivery_id,
#             rider_id=rider_id,
#         )

#         return result_data

#     except Exception as e:
#         logger.error(
#             "pickup_delivery_error",
#             delivery_id=delivery_id,
#             error=str(e),
#             exc_info=True,
#         )
#         raise


# async def complete_delivery(
#     delivery_id: str,
#     sender_id: str,
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ) -> dict:
#     """
#     Sender completes delivery.
#     - Releases both escrows
#     - Pays dispatch
#     - Updates transactions to ESCROW_RELEASE
#     - Logs platform commission
#     - Frees up rider
#     """
#     logger.info(
#         "complete_delivery_called",
#         delivery_id=delivery_id,
#         sender_id=sender_id,
#     )

#     try:
#         # Call atomic RPC
#         result = await supabase.rpc("mark_delivery_as_completed", {
#             "p_delivery_id": delivery_id,
#             "p_sender_id": sender_id,
#         }).execute()

#         result_data = result.data

#         if result.error:
#             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, result.error.message)

#         # Notify dispatch
#         await notify_user(
#             user_id=result_data["dispatch_id"],
#             title="Delivery Completed",
#             body=f"Payment of ₦{result_data['amount_released']} released",
#             data={
#                 "delivery_id": delivery_id,
#                 "type": "DELIVERY_COMPLETED",
#                 "amount": str(result_data["amount_released"]),
#             },
#             supabase=supabase,
#         )

#         # Notify rider
#         if result_data.get("rider_id"):
#             await notify_user(
#                 user_id=result_data["rider_id"],
#                 title="Delivery Completed",
#                 body="Delivery marked as completed by sender",
#                 data={
#                     "delivery_id": delivery_id,
#                     "type": "DELIVERY_COMPLETED",
#                 },
#                 supabase=supabase,
#             )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type="DELIVERY_ORDER",
#             entity_id=delivery_id,
#             action="COMPLETED",
#             old_value={"status": "DELIVERED"},
#             new_value={"status": "COMPLETED", "escrow": "RELEASED"},
#             actor_id=sender_id,
#             actor_type="USER",
#             change_amount=Decimal(str(result_data["amount_released"])),
#             notes="Delivery completed, escrow released to dispatch",
#             request=request,
#         )

#         logger.info(
#             "complete_delivery_success",
#             delivery_id=delivery_id,
#             amount_released=str(result_data["amount_released"]),
#         )

#         return result_data

#     except Exception as e:
#         logger.error(
#             "complete_delivery_error",
#             delivery_id=delivery_id,
#             error=str(e),
#             exc_info=True,
#         )
#         raise


# async def cancel_delivery(
#     delivery_id: str,
#     triggered_by_user_id: str,
#     cancellation_reason: Optional[str],
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ) -> dict:
#     """
#     Sender or Rider cancels delivery.
#     - If after pickup by sender: Requires return (no refund, delivery continues)
#     - If before pickup or by rider: Full cancellation with refund
#     """
#     logger.info(
#         "cancel_delivery_called",
#         delivery_id=delivery_id,
#         triggered_by=triggered_by_user_id,
#     )

#     try:
#         # Call atomic RPC
#         result = await supabase.rpc("mark_delivery_as_cancelled", {
#             "p_delivery_id": delivery_id,
#             "p_triggered_by_user_id": triggered_by_user_id,
#             "p_cancellation_reason": cancellation_reason,
#         }).execute()

#         if result.error:
#             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, result.error.message)

#         result_data = result.data
#         cancelled_by = result_data["cancelled_by"]
#         requires_return = result_data.get("requires_return", False)

#         # Send appropriate notifications
#         if requires_return:
#             # Sender cancelled after pickup - notify rider to return
#             if result_data.get("rider_id"):
#                 await notify_user(
#                     user_id=result_data["rider_id"],
#                     title="Delivery Cancelled - Return Required",
#                     body="Sender cancelled. Please return the item to sender.",
#                     data={
#                         "delivery_id": delivery_id,
#                         "type": "DELIVERY_CANCELLED_RETURN",
#                         "requires_return": True,
#                     },
#                     supabase=supabase,
#                 )
#         else:
#             # Full cancellation - notify both parties
#             if cancelled_by == "RIDER":
#                 # Notify sender that rider cancelled
#                 await notify_user(
#                     user_id=result_data["sender_id"],
#                     title="Delivery Cancelled",
#                     body=f"Rider cancelled your delivery. Refund: ₦{result_data['refund_amount']}",
#                     data={
#                         "delivery_id": delivery_id,
#                         "type": "DELIVERY_CANCELLED",
#                         "refund_amount": str(result_data["refund_amount"]),
#                     },
#                     supabase=supabase,
#                 )
#             else:
#                 # Notify rider that sender cancelled
#                 if result_data.get("rider_id"):
#                     await notify_user(
#                         user_id=result_data["rider_id"],
#                         title="Delivery Cancelled",
#                         body="Sender cancelled the delivery",
#                         data={
#                             "delivery_id": delivery_id,
#                             "type": "DELIVERY_CANCELLED",
#                         },
#                         supabase=supabase,
#                     )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type="DELIVERY_ORDER",
#             entity_id=delivery_id,
#             action="CANCELLED",
#             new_value={
#                 "status": "CANCELLED",
#                 "cancelled_by": cancelled_by,
#                 "requires_return": requires_return,
#             },
#             actor_id=triggered_by_user_id,
#             actor_type="USER",
#             change_amount=Decimal(str(result_data["refund_amount"])) if result_data["refund_amount"] > 0 else None,
#             notes=result_data["message"],
#             request=request,
#         )

#         logger.info(
#             "cancel_delivery_success",
#             delivery_id=delivery_id,
#             cancelled_by=cancelled_by,
#             requires_return=requires_return,
#             refund_amount=str(result_data["refund_amount"]),
#         )

#         return result_data

#     except Exception as e:
#         logger.error(
#             "cancel_delivery_error",
#             delivery_id=delivery_id,
#             error=str(e),
#             exc_info=True,
#         )
#         raise


# async def decline_delivery_assignment(
#     delivery_id: str,
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ) -> dict:
#     """
#     Rider declines delivery assignment.
#     - Clears rider_id and dispatch_id
#     - Sets status back to PENDING
#     - No wallet operations
#     """
#     logger.info(
#         "decline_delivery_called",
#         delivery_id=delivery_id,
#     )

#     try:
#         # Call atomic RPC
#         result = await supabase.rpc("clear_rider_assignment", {
#             "p_delivery_id": delivery_id,
#         }).execute()

#         result_data = result.data

#         if result.error:
#             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, result.error.message)

#         logger.info(
#             "decline_delivery_success",
#             delivery_id=delivery_id,
#         )

#         return result_data

#     except Exception as e:
#         logger.error(
#             "decline_delivery_error",
#             delivery_id=delivery_id,
#             error=str(e),
#             exc_info=True,
#         )
#         raise

    


# # ───────────────────────────────────────────────
# # 3. Assign Rider After Payment (RPC already updated earlier)
# # ───────────────────────────────────────────────
# async def assign_rider_to_order(
#     tx_ref: UUID, rider_id: UUID, supabase: AsyncClient
# ) -> AssignRiderResponse:
#     try:

#         assign_resp = await supabase.rpc(
#             "assign_rider_to_delivery",
#             {"p_tx_ref": str(tx_ref), "p_rider_id": str(rider_id)},
#         ).execute()

#         if assign_resp.error:
#             raise HTTPException(500, assign_resp.error.message)
        

#         result = assign_resp.data

#         # Notify rider on success
#         if assign_resp.data:
#             await notify_user(
#                 user_id=rider_id,
#                 title="New Delivery Assigned!",
#                 body="You have a new order to pickup",
#                 data={"order_id": str(tx_ref), "type": "DELIVERY_ASSIGNED"},
#                 supabase=supabase,
#             )

#         return AssignRiderResponse(
#             success=result["success"],
#             message=result["message"],
#             delivery_status=result.get("delivery_status", "ASSIGNED"),
#             rider_name=result.get("rider_name"),
#         )

#     except Exception as e:
#         error_msg = str(e)
#         if (
#             "Rider is currently suspended" in error_msg
#             or "Rider is blocked" in error_msg
#             or "Rider not available" in error_msg
#             or "Rider limited to 1 delivery per day" in error_msg
#         ):
#             raise HTTPException(status.HTTP_400_BAD_REQUEST, error_msg)
#         raise HTTPException(
#             status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to assign rider"
#         )


# async def assign_rider_to_order2(
#     order_id: UUID, data: AssignRiderRequest, sender_id: UUID, supabase: AsyncClient
# ) -> AssignRiderResponse:
#     try:
#         order = (
#             await supabase.table("delivery_orders")
#             .select("id, sender_id, status")
#             .eq("id", str(order_id))
#             .single()
#             .execute()
#         )

#         if not order.data:
#             raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery order not found")

#         if order.data["sender_id"] != str(sender_id):
#             raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your order")

#         if order.data["status"] != "PAID_NEEDS_RIDER":
#             raise HTTPException(
#                 status.HTTP_400_BAD_REQUEST,
#                 "Order already has a rider or is not ready for assignment",
#             )

#         assign_resp = await supabase.rpc(
#             "assign_rider_to_paid_delivery",
#             {"p_order_id": str(order_id), "p_chosen_rider_id": str(data.rider_id)},
#         ).execute()

#         result = assign_resp.data

#         # Notify rider on success
#         if result["success"]:
#             await notify_user(
#                 user_id=data.rider_id,
#                 title="New Delivery Assigned!",
#                 body="You have a new order to pick up",
#                 data={"order_id": str(order_id), "type": "DELIVERY_ASSIGNED"},
#                 supabase=supabase,
#             )

#         return AssignRiderResponse(
#             success=result["success"],
#             message=result["message"],
#             delivery_status=result.get("delivery_status", "ASSIGNED"),
#             rider_name=result.get("rider_name"),
#         )

#     except Exception as e:
#         error_msg = str(e)
#         if (
#             "Rider is currently suspended" in error_msg
#             or "Rider is blocked" in error_msg
#             or "Rider not available" in error_msg
#             or "Rider limited to 1 delivery per day" in error_msg
#         ):
#             raise HTTPException(status.HTTP_400_BAD_REQUEST, error_msg)
#         raise HTTPException(
#             status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to assign rider"
#         )


# # ───────────────────────────────────────────────
# # 4. Rider Delivery Action (accept/decline)
# # ───────────────────────────────────────────────
# async def rider_delivery_action(
#     order_id: UUID, data: DeliveryAction, rider_id: UUID, supabase: AsyncClient
# ) -> DeliveryActionResponse:
#     try:
#         order = (
#             await supabase.table("delivery_orders")
#             .select("id, rider_id, status")
#             .eq("id", str(order_id))
#             .single()
#             .execute()
#         )

#         if not order.data:
#             raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery order not found")

#         if order.data["rider_id"] != str(rider_id):
#             raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your delivery order")

#         if order.data["delivery_status"] != "ASSIGNED":
#             raise HTTPException(
#                 status.HTTP_400_BAD_REQUEST, f"Order is {order['status']}, cannot act"
#             )

#         new_status = "PICKED_UP" if data.accept else "PAID_NEEDS_RIDER"

#         await (
#             supabase.table("delivery_orders")
#             .update({"status": new_status})
#             .eq("id", str(order_id))
#             .execute()
#         )

#         message = (
#             "Delivery accepted successfully!" if data.accept else "Delivery declined"
#         )

#         return DeliveryActionResponse(
#             delivery_id=order_id,
#             order_id=order_id,
#             delivery_status=new_status,
#             message=message,
#         )

#     except Exception as e:
#         raise HTTPException(
#             status.HTTP_500_INTERNAL_SERVER_ERROR, f"Action failed: {str(e)}"
#         )


# # ───────────────────────────────────────────────
# # 5. Rider Pickup
# # ───────────────────────────────────────────────
# async def rider_picked_up(
#     order_id: UUID,
#     rider_id: UUID,
#     supabase: AsyncClient,
# ):
#     try:
#         order = (
#             await supabase.table("delivery_orders")
#             .select("id, status, rider_id, sender_id, dispatch_id, delivery_fee")
#             .eq("id", str(order_id))
#             .single()
#             .execute()
#         ).data

#         if not order:
#             raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery order not found")

#         if order["rider_id"] != str(rider_id):
#             raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your delivery order")

#         if order["status"] not in ("ASSIGNED", "PICKED_UP"):
#             raise HTTPException(
#                 status.HTTP_400_BAD_REQUEST,
#                 f"Cannot pick up. Current status: {order['status']}",
#             )

#         full_amount = order["delivery_fee"]
#         dispatch_id = order["dispatch_id"]

#         # Credit dispatch escrow (virtual claim)
#         credit_resp = await supabase.rpc(
#             "credit_dispatch_escrow_on_pickup",
#             {
#                 "p_dispatch_id": str(dispatch_id),
#                 "p_full_amount": full_amount,
#             },
#         ).execute()

#         result = credit_resp.data

#         if not result.get("success", False):
#             raise HTTPException(
#                 status.HTTP_400_BAD_REQUEST,
#                 result.get("message", "Failed to credit dispatch escrow"),
#             )

#         # Update status to IN_TRANSIT
#         await (
#             supabase.table("delivery_orders")
#             .update({"status": "IN_TRANSIT"})
#             .eq("id", str(order_id))
#             .execute()
#         )

#         # Notify sender
#         await notify_user(
#             user_id=UUID(order["sender_id"]),
#             title="Package Picked Up!",
#             body="The rider has picked up your package and is on the way.",
#             data={"order_id": str(order_id), "type": "DELIVERY_PICKED_UP"},
#             supabase=supabase,
#         )

#         return {
#             "success": True,
#             "message": "Package picked up. Dispatch escrow credited (virtual hold).",
#             "status": "IN_TRANSIT",
#             "full_fee_credited_to_dispatch_escrow": full_amount,
#         }

#     except Exception as e:
#         raise HTTPException(500, f"Pickup failed: {str(e)}")


# # ───────────────────────────────────────────────
# # 6. Rider Confirm Delivery (Delivered)
# # ───────────────────────────────────────────────
# async def rider_confirm_delivery(
#     order_id: UUID,
#     rider_id: UUID,
#     supabase: AsyncClient,
# ):
#     try:
#         order = (
#             await supabase.table("delivery_orders")
#             .select("id, status, rider_id")
#             .eq("id", str(order_id))
#             .single()
#             .execute()
#         )

#         if not order.data:
#             raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery order not found")

#         if order.data["rider_id"] != str(rider_id):
#             raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your delivery order")

#         if order.data["status"] != "IN_TRANSIT":
#             raise HTTPException(
#                 status.HTTP_400_BAD_REQUEST,
#                 f"Cannot confirm delivery. Current status: {order['status']}",
#             )

#         await (
#             supabase.table("delivery_orders")
#             .update({"status": "DELIVERED"})
#             .eq("id", str(order_id))
#             .execute()
#         )

#         # Notify sender
#         # We need sender_id, let's get it if not available
#         sender_id_resp = (
#             await supabase.table("delivery_orders")
#             .select("sender_id")
#             .eq("id", str(order_id))
#             .single()
#             .execute()
#         )
#         if sender_id_resp.data:
#             await notify_user(
#                 user_id=UUID(sender_id_resp.data["sender_id"]),
#                 title="Package Delivered!",
#                 body="Your package has been delivered. Please confirm receipt to release payment.",
#                 data={"order_id": str(order_id), "type": "DELIVERY_DELIVERED"},
#                 supabase=supabase,
#             )

#         return {
#             "success": True,
#             "message": "Delivery confirmed! Waiting for sender to confirm receipt.",
#             "status": "DELIVERED",
#         }

#     except Exception as e:
#         raise HTTPException(
#             status.HTTP_500_INTERNAL_SERVER_ERROR,
#             f"Delivery confirmation failed: {str(e)}",
#         )


# # ───────────────────────────────────────────────
# # 7. Sender Confirm Receipt (Release Payment)
# # ───────────────────────────────────────────────
# async def sender_confirm_receipt(
#     order_id: UUID,
#     sender_id: UUID,
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ):
#     logger.info(
#         "sender_confirm_receipt", order_id=str(order_id), sender_id=str(sender_id)
#     )
#     try:
#         order = (
#             await supabase.table("delivery_orders")
#             .select(
#                 "id, sender_id, status, dispatch_id, delivery_fee, amount_due_dispatch"
#             )
#             .eq("id", str(order_id))
#             .single()
#             .execute()
#         ).data

#         if not order:
#             raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery order not found")

#         if order["sender_id"] != str(sender_id):
#             raise HTTPException(
#                 status.HTTP_403_FORBIDDEN, "You are not the sender of this package"
#             )

#         if order["status"] != "DELIVERED":
#             raise HTTPException(
#                 status.HTTP_400_BAD_REQUEST,
#                 f"Cannot confirm receipt. Current status: {order['status']}",
#             )

#         delivery_fee = order["delivery_fee"]
#         amount_due_dispatch = order["amount_due_dispatch"]
#         platform_fee = delivery_fee - amount_due_dispatch

#         dispatch_id = order["dispatch_id"]

#         # Release from dispatch escrow → dispatch balance + platform fee
#         release_resp = await supabase.rpc(
#             "release_from_dispatch_escrow",
#             {
#                 "p_dispatch_id": str(dispatch_id),
#                 "p_full_amount": delivery_fee,
#                 "p_dispatch_amount": amount_due_dispatch,
#             },
#         ).execute()

#         result = release_resp.data

#         if not result.get("success", False):
#             raise HTTPException(
#                 status.HTTP_400_BAD_REQUEST,
#                 result.get("message", "Failed to release funds"),
#             )

#         await (
#             supabase.table("delivery_orders")
#             .update({"status": "COMPLETED"})
#             .eq("id", str(order_id))
#             .execute()
#         )

#         # Increment rider total deliveries
#         if order.get("rider_id"):
#             await supabase.rpc(
#                 "increment_rider_total_delivery", {"p_rider_id": str(order["rider_id"])}
#             ).execute()

#         # Notify rider/dispatch
#         if order.get("rider_id"):
#             await notify_user(
#                 user_id=UUID(order["rider_id"]),
#                 title="Delivery Completed!",
#                 body=f"The sender has confirmed receipt. NGN {amount_due_dispatch} has been added to your balance.",
#                 data={"order_id": str(order_id), "type": "DELIVERY_COMPLETED"},
#                 supabase=supabase,
#             )

#         # Log platform commission
#         await (
#             supabase.table("platform_commissions")
#             .insert(
#                 {
#                     "to_user_id": order["dispatch_id"],
#                     "from_user_id": order["sender_id"],
#                     "order_id": str(order_id),
#                     "service_type": "DELIVERY",
#                     "description": f"Platform commission from delivery order {order_id} (₦{platform_fee})",
#                 }
#             )
#             .execute()
#         )

#         logger.info(
#             "sender_confirm_receipt_success",
#             order_id=str(order_id),
#             dispatch_amount=float(amount_due_dispatch),
#             platform_fee=Decimal(delivery_fee),
#         )

#         return {
#             "success": True,
#             "message": "Receipt confirmed! Dispatch paid commission, platform kept fee remainder.",
#             "status": "COMPLETED",
#             "dispatch_received": amount_due_dispatch,
#             "platform_fee": platform_fee,
#             "total_cleared_from_sender_escrow": delivery_fee,
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(
#             "sender_confirm_receipt_error",
#             order_id=str(order_id),
#             error=str(e),
#             exc_info=True,
#         )
#         raise HTTPException(
#             status.HTTP_500_INTERNAL_SERVER_ERROR, f"Confirmation failed: {str(e)}"
#         )


# # ───────────────────────────────────────────────
# # 8. Cancel Delivery
# # ───────────────────────────────────────────────
# async def cancel_delivery(
#     order_id: UUID,
#     data: DeliveryCancelRequest,
#     current_user_id: UUID,
#     current_user_type: str,
#     supabase: AsyncClient,
# ) -> DeliveryCancelResponse:
#     try:
#         order = (
#             await supabase.table("delivery_orders")
#             .select("status, sender_id, rider_id")
#             .eq("id", str(order_id))
#             .single()
#             .execute()
#         ).data

#         if not order:
#             raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery order not found")

#         is_sender = str(current_user_id) == order["sender_id"]
#         is_rider = (
#             current_user_type == "RIDER" and str(current_user_id) == order["rider_id"]
#         )

#         if not (is_sender or is_rider):
#             raise HTTPException(
#                 status.HTTP_403_FORBIDDEN, "You cannot cancel this delivery"
#             )

#         cancelled_by = "SENDER" if is_sender else "RIDER"

#         if order["status"] in ("DELIVERED", "COMPLETED"):
#             raise HTTPException(
#                 status.HTTP_400_BAD_REQUEST, "Cannot cancel completed delivery"
#             )

#         await (
#             supabase.table("delivery_orders")
#             .update(
#                 {
#                     "status": "CANCELLED",
#                     "cancelled_by": cancelled_by,
#                     "cancel_reason": data.reason,
#                     "cancelled_at": "now()",
#                 }
#             )
#             .eq("id", str(order_id))
#             .execute()
#         )

#         refunded = order["status"] in ("PAID_NEEDS_RIDER", "ASSIGNED")

#         message = (
#             "Delivery cancelled. Full refund processed."
#             if refunded
#             else "Delivery cancelled. Rider will return item. You will pay delivery fee on receipt confirmation."
#         )

#         return DeliveryCancelResponse(
#             order_id=order_id,
#             delivery_status="CANCELLED",
#             refunded=refunded,
#             message=message,
#         )

#     except Exception as e:
#         raise HTTPException(500, f"Cancel failed: {str(e)}")


# # ───────────────────────────────────────────────
# # 9. Get Delivery Orders
# # ───────────────────────────────────────────────
# async def get_delivery_orders(
#     current_user_id: UUID,
#     is_admin: bool,
#     limit: int = 20,
#     offset: int = 0,
#     status_filter: Optional[str] = None,
#     supabase=None,
# ) -> DeliveryOrdersResponse:
#     try:
#         query = (
#             supabase.table("delivery_orders")
#             .select("""
#                 id,
#                 order_number,
#                 sender_id,
#                 receiver_phone,
#                 pickup_location,
#                 destination,
#                 delivery_fee,
#                 total_price,
#                 status,
#                 payment_status,
#                 escrow_status,
#                 rider_id,
#                 dispatch_id,
#                 rider_phone_number,
#                 created_at,
#                 updated_at,
#                 package_image_url,
#                 image_url,
#                 profiles!inner(full_name as rider_name)  # rider name
#             """)
#             .order("status", desc=False)
#             .order("created_at", desc=True)
#             .range(offset, offset + limit - 1)
#         )

#         if not is_admin:
#             query = query.or_(
#                 f"sender_id.eq.{current_user_id},"
#                 f"rider_id.eq.{current_user_id},"
#                 f"dispatch_id.eq.{current_user_id}"
#             )

#         if status_filter:
#             query = query.eq("status", status_filter)

#         resp = await query.execute()
#         orders = resp.data or []

#         count_query = supabase.table("delivery_orders").select("count", count="exact")
#         if not is_admin:
#             count_query = count_query.or_(
#                 f"sender_id.eq.{current_user_id},"
#                 f"rider_id.eq.{current_user_id},"
#                 f"dispatch_id.eq.{current_user_id}"
#             )
#         total_count = (await count_query.execute()).count or 0

#         return DeliveryOrdersResponse(
#             orders=[DeliveryOrderListItem(**o) for o in orders],
#             total_count=total_count,
#             has_more=(offset + len(orders)) < total_count,
#         )

#     except Exception as e:
#         raise HTTPException(500, f"Failed to fetch delivery orders: {str(e)}")
