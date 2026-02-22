from uuid import UUID
from typing import Optional
from decimal import Decimal
from supabase import AsyncClient
from fastapi import HTTPException, status, Request
from enum import Enum
from app.config.logging import logger
from app.utils.audit import log_audit_event
from pydantic import BaseModel
from app.services.notification_service import notify_user
from app.config.config import settings
from postgrest.exceptions import APIError
from app.services.payment_service import process_successful_delivery_payment, process_successful_food_payment, process_successful_topup_payment, process_successful_laundry_payment, process_successful_product_payment

HANDLER_MAP = {
    "FOOD-": process_successful_food_payment,
    "PRODUCT-": process_successful_product_payment,
    "LAUNDRY-": process_successful_laundry_payment,
    "DELIVERY-": process_successful_delivery_payment,
    "TOPUP-": process_successful_topup_payment,
}


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PREPARING = "PREPARING"
    READY = "READY"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"


class TransactionType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "RWITHDRAWAL"
    ESCROW_RELEASE = "ESCROW_RELEASE"
    ESCROW_HOLD = "ESCROW_HOLD"
    REFUNDED = "REFUNDED"

class ProcessPaymentRequest(BaseModel):
    tx_ref: str
    paid_amount: float
    flw_ref: str
    payment_method: str  # 'CARD' or 'WALLET'


class OrderStatusUpdate(BaseModel):
    status: str | None = "success"
    new_status: OrderStatus
    cancel_reason: Optional[str] = None


async def process_payment(
    data: ProcessPaymentRequest,
    x_internal_key: str,
    supabase: AsyncClient ,
):
    # 1. Verify internal key — only Edge Function can call this
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    # 2. Find handler from tx_ref prefix
    handler = next(
        (h for prefix, h in HANDLER_MAP.items() if data.tx_ref.startswith(prefix)),
        None
    )

    if not handler:
        logger.warning("unknown_tx_ref_prefix", tx_ref=data.tx_ref)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tx_ref prefix: {data.tx_ref}",
        )

    # 3. Run the handler
    try:
        await handler(
            tx_ref=data.tx_ref,
            paid_amount=data.paid_amount,
            flw_ref=data.flw_ref,
            payment_method=data.payment_method,
            supabase=supabase,
        )

        logger.info(
            "payment_processed",
            tx_ref=data.tx_ref,
            handler=handler.__name__,
        )

        return {"status": "success", "tx_ref": data.tx_ref}

    except APIError as e:
        logger.error(
            "payment_processing_failed",
            tx_ref=data.tx_ref,
            error=str(e),
            exc_info=True,
        )
        # Return 500 so Edge Function leaves message in queue for retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Something went wrong while processing the payment. Please try again.',
        )


async def update_order_status(
    order_id: str,
    data: OrderStatusUpdate,
    entity_type: str,
    triggered_by_user_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """Update order status with proper authorization and wallet handling."""

    order_type = entity_type.replace("_ORDER", "")  # 'FOOD_ORDER' -> 'FOOD'

    try:
        # Handle COMPLETED status
        if data.new_status == OrderStatus.COMPLETED:
            result = await supabase.rpc(
                "mark_order_as_completed",
                {
                    "p_order_id": f"{order_id}",
                    "p_order_type": order_type,
                    "p_triggered_by_user_id": f"{triggered_by_user_id}",
                },
            ).execute()

            result_data = result.data

            # Audit log
            await log_audit_event(
                supabase,
                entity_type=entity_type,
                entity_id=str(order_id),
                action="ORDER_COMPLETED",
                old_value={"status": "DELIVERED"},
                new_value={"status": "COMPLETED", "escrow": "RELEASED"},
                actor_id=str(triggered_by_user_id),
                actor_type="USER",
                change_amount=Decimal(str(result_data["amount_released"])),
                notes="Order completed by customer, escrow released to vendor",
                request=request,
            )

            # Notify participants
            await notify_user(
                result_data["customer_id"],
                "Order Completed",
                "Transaction completed",
                data={"SUCCESS": "Transaction completed"},
                supabase=supabase,
            )

            await notify_user(
                result_data["vendor_id"],
                "Order Completed",
                "Transaction completed",
                data={"SUCCESS": "Transaction completed"},
                supabase=supabase,
            )

            logger.info(
                "order_completed",
                order_id=order_id,
                amount_released=str(result_data["amount_released"]),
            )

            return result_data

        # Handle CANCELLED status
        elif data.new_status == OrderStatus.CANCELLED:
            result = await supabase.rpc(
                "mark_order_as_cancelled",
                {
                    "p_order_id": order_id,
                    "p_order_type": order_type,
                    "p_triggered_by_user_id": triggered_by_user_id,
                    "p_cancellation_reason": data.cancel_reason,
                },
            ).execute()

            result_data = result.data

            # Audit log
            await log_audit_event(
                supabase,
                entity_type=entity_type,
                entity_id=str(order_id),
                action="ORDER_CANCELLED",
                old_value={"status": "PENDING", "payment_status": "SUCCESS"},
                new_value={"status": "CANCELLED", "payment_status": "REFUNDED"},
                actor_id=str(triggered_by_user_id),
                actor_type="USER",
                change_amount=Decimal(str(result_data.get("refund_amount", 0))),
                notes=data.cancel_reason or "Order cancelled",
                request=request,
            )

            logger.info(
                "order_cancelled",
                order_id=order_id,
                refund_amount=str(result_data.get("refund_amount", 0)),
            )

            return result_data

        # Handle simple status updates (PREPARING, READY, IN_TRANSIT, DELIVERED)
        else:
            result = await supabase.rpc(
                "update_order_status_simple",
                {
                    "p_order_id": order_id,
                    "p_order_type": order_type,
                    "p_new_status": data.new_status.value,
                    "p_triggered_by_user_id": triggered_by_user_id,
                },
            ).execute()

            result_data = result.data

            if not result_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Order {order_id} ({order_type}) not found or update ignored.",
                )

            # Audit log
            await log_audit_event(
                supabase,
                entity_type=entity_type,
                entity_id=str(order_id),
                action="STATUS_CHANGED",
                old_value={"status": "previous"},
                new_value={"status": data.new_status.value},
                actor_id=str(triggered_by_user_id),
                actor_type="USER",
                notes=f"Order status changed to {data.new_status.value}",
                request=request,
            )

            logger.info(
                "order_status_updated",
                order_id=order_id,
                new_status=data.new_status.value,
            )

            return result_data

    except Exception as e:
        logger.error(f"Order update failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class DeliveryStatusUpdate(BaseModel):
    new_status: DeliveryStatus
    cancellation_reason: Optional[str] = None
    decline_reason: Optional[str] = None


async def update_delivery_status(
    delivery_id: str,
    data: DeliveryStatusUpdate,
    triggered_by_user_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """
    Smart delivery status update with role-based authorization and wallet handling.
    Routes to appropriate atomic RPC based on status.
    """
    logger.info(
        "update_delivery_status_called",
        delivery_id=delivery_id,
        new_status=data.new_status.value,
        triggered_by=triggered_by_user_id,
    )

    try:
        # FIRST: Fetch delivery to check authorization
        delivery_resp = (
            await supabase.table("delivery_orders")
            .select(
                "id, sender_id, rider_id, dispatch_id, delivery_status, order_number"
            )
            .eq("id", delivery_id)
            .single()
            .execute()
        )

        if not delivery_resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found"
            )

        delivery = delivery_resp.data
        current_status = delivery["delivery_status"]

        # AUTHORIZATION CHECKS
        _validate_authorization(
            new_status=data.new_status,
            triggered_by_user_id=triggered_by_user_id,
            sender_id=delivery["sender_id"],
            rider_id=delivery["rider_id"],
            dispatch_id=delivery["dispatch_id"],
        )

        # STATE TRANSITION VALIDATION
        _validate_state_transition(current_status, data.new_status.value)

        # Route to appropriate handler
        if data.new_status == DeliveryStatus.PICKED_UP:
            result_data = await _handle_pickup(
                delivery_id, triggered_by_user_id, supabase, request
            )

        elif data.new_status == DeliveryStatus.COMPLETED:
            result_data = await _handle_completion(
                delivery_id, triggered_by_user_id, supabase, request
            )

        elif data.new_status == DeliveryStatus.CANCELLED:
            result_data = await _handle_cancellation(
                delivery_id,
                triggered_by_user_id,
                data.cancellation_reason,
                supabase,
                request,
            )

        elif data.new_status == DeliveryStatus.DECLINED:
            result_data = await _handle_decline(delivery_id, supabase, request)

        else:
            # Simple status updates (ASSIGNED, ACCEPTED, IN_TRANSIT, DELIVERED)
            result_data = await _handle_simple_status(
                delivery_id,
                data.new_status.value,
                triggered_by_user_id,
                supabase,
                request,
            )

        logger.info(
            "update_delivery_status_success",
            delivery_id=delivery_id,
            new_status=data.new_status.value,
        )

        return result_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "update_delivery_status_failed",
            delivery_id=delivery_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update delivery status: {str(e)}",
        )


# ============================================================
# AUTHORIZATION VALIDATION
# ============================================================


def _validate_authorization(
    new_status: DeliveryStatus,
    triggered_by_user_id: str,
    sender_id: str,
    rider_id: Optional[str],
    dispatch_id: Optional[str],
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


# ============================================================
# INTERNAL HANDLERS (Same as before, no changes)
# ============================================================


async def _handle_pickup(
    delivery_id: str,
    rider_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """Rider picks up delivery - creates escrow holds"""
    result = await supabase.rpc(
        "mark_delivery_as_picked_up",
        {
            "p_delivery_id": delivery_id,
            "p_rider_id": rider_id,
        },
    ).execute()

    result_data = result.data
    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {result.error.message}",
        )

    await notify_user(
        user_id=result_data["sender_id"],
        title="Delivery Picked Up",
        body="Your delivery has been picked up by the rider",
        data={"delivery_id": delivery_id, "type": "DELIVERY_PICKED_UP"},
        supabase=supabase,
    )

    return result_data


async def _handle_completion(
    delivery_id: str,
    sender_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """Sender completes delivery - releases escrow and pays dispatch"""
    result = await supabase.rpc(
        "mark_delivery_as_completed",
        {
            "p_delivery_id": delivery_id,
            "p_sender_id": sender_id,
        },
    ).execute()

    result_data = result.data

    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {result.error.message}",
        )

    await notify_user(
        user_id=result_data["dispatch_id"],
        title="Delivery Completed",
        body=f"Payment of ₦{result_data['amount_released']} released",
        data={
            "delivery_id": delivery_id,
            "type": "DELIVERY_COMPLETED",
            "amount": str(result_data["amount_released"]),
        },
        supabase=supabase,
    )

    if result_data.get("rider_id"):
        await notify_user(
            user_id=result_data["rider_id"],
            title="Delivery Completed",
            body="Delivery marked as completed by sender",
            data={"delivery_id": delivery_id, "type": "DELIVERY_COMPLETED"},
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
        notes="Delivery completed, escrow released to dispatch",
        request=request,
    )

    return result_data


async def _handle_cancellation(
    delivery_id: str,
    triggered_by_user_id: str,
    cancellation_reason: Optional[str],
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """Sender or Rider cancels delivery - handles refunds and returns"""
    result = await supabase.rpc(
        "mark_delivery_as_cancelled",
        {
            "p_delivery_id": delivery_id,
            "p_triggered_by_user_id": triggered_by_user_id,
            "p_cancellation_reason": cancellation_reason,
        },
    ).execute()

    if result.error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {result.error.message}",
        )

    result_data = result.data
    cancelled_by = result_data["cancelled_by"]
    requires_return = result_data.get("requires_return", False)

    if requires_return:
        if result_data.get("rider_id"):
            await notify_user(
                user_id=result_data["rider_id"],
                title="Delivery Cancelled - Return Required",
                body="Sender cancelled. Please return the item to sender.",
                data={
                    "delivery_id": delivery_id,
                    "type": "DELIVERY_CANCELLED_RETURN",
                    "requires_return": True,
                },
                supabase=supabase,
            )
    else:
        if cancelled_by == "RIDER":
            await notify_user(
                user_id=result_data["sender_id"],
                title="Delivery Cancelled",
                body=f"Rider cancelled your delivery. Refund: ₦{result_data['refund_amount']}",
                data={
                    "delivery_id": delivery_id,
                    "type": "DELIVERY_CANCELLED",
                    "refund_amount": str(result_data["refund_amount"]),
                },
                supabase=supabase,
            )
        else:
            if result_data.get("rider_id"):
                await notify_user(
                    user_id=result_data["rider_id"],
                    title="Delivery Cancelled",
                    body="Sender cancelled the delivery",
                    data={"delivery_id": delivery_id, "type": "DELIVERY_CANCELLED"},
                    supabase=supabase,
                )

    await log_audit_event(
        supabase,
        entity_type="DELIVERY_ORDER",
        entity_id=delivery_id,
        action="CANCELLED",
        new_value={
            "status": "CANCELLED",
            "cancelled_by": cancelled_by,
            "requires_return": requires_return,
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


async def _handle_decline(
    delivery_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """Rider declines assignment - clears rider details"""
    result = await supabase.rpc(
        "clear_rider_assignment",
        {
            "p_delivery_id": delivery_id,
        },
    ).execute()

    result_data = result.data

    if result.error:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, result.error.message)

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


async def _handle_simple_status(
    delivery_id: str,
    new_status: str,
    triggered_by_user_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """Handle simple status updates (ASSIGNED, ACCEPTED, IN_TRANSIT, DELIVERED)"""
    result = await supabase.rpc(
        "update_delivery_status_simple",
        {
            "p_delivery_id": delivery_id,
            "p_new_status": new_status,
            "p_triggered_by_user_id": triggered_by_user_id,
        },
    ).execute()

    if result.error:
        raise HTTPException(status_code=500, detail=f"Error: {result.error.message}")

    result_data = result.data

    return result_data


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
