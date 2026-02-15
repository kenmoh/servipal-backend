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


class OrderStatusUpdate(BaseModel):
    status: str | None = "success"
    new_status: OrderStatus
    cancel_reason: Optional[str] = None


async def update_order_status(
    order_id: UUID,
    data: OrderStatusUpdate,
    entity_type: str,
    triggered_by_user_id: UUID,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """Update order status with proper authorization and wallet handling."""
    
    order_type = entity_type.replace('_ORDER', '')  # 'FOOD_ORDER' -> 'FOOD'
    
    try:
        # Handle COMPLETED status
        if data.new_status == OrderStatus.COMPLETED:
            logger.info(
                    "CALLING_COMPLETE_RPC",
                    order_id=order_id,
                    order_id_type=type(order_id).__name__,
                    order_id_repr=repr(order_id),
                    order_type=order_type,
                    triggered_by=triggered_by_user_id,
                )
            result = await supabase.rpc("mark_order_as_completed", {
                "p_order_id": f'{order_id}',
                "p_order_type": order_type,
                "p_triggered_by_user_id": f'{triggered_by_user_id}',
            }).execute()
            
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
                change_amount=Decimal(str(result_data['amount_released'])),
                notes="Order completed by customer, escrow released to vendor",
                request=request,
            )
            
            # Notify participants
            await notify_user(
                result_data['customer_id'],
                "Order Completed",
                "Transaction completed",
                data={"SUCCESS": "Transaction completed"},
                supabase=supabase,
            )
            
            await notify_user(
                result_data['vendor_id'],
                "Order Completed",
                "Transaction completed",
                data={"SUCCESS": "Transaction completed"},
                supabase=supabase,
            )
            
            logger.info(
                "order_completed",
                order_id=order_id,
                amount_released=str(result_data['amount_released']),
            )
            
            return result_data
        
        # Handle CANCELLED status
        elif data.new_status == OrderStatus.CANCELLED:
            result = await supabase.rpc("mark_order_as_cancelled", {
                "p_order_id": order_id,
                "p_order_type": order_type,
                "p_triggered_by_user_id": triggered_by_user_id,
                "p_cancellation_reason": data.cancel_reason,
            }).execute()
            
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
                change_amount=Decimal(str(result_data.get('refund_amount', 0))),
                notes=data.cancel_reason or "Order cancelled",
                request=request,
            )
            
            logger.info(
                "order_cancelled",
                order_id=order_id,
                refund_amount=str(result_data.get('refund_amount', 0)),
            )
            
            return result_data
        
        # Handle simple status updates (PREPARING, READY, IN_TRANSIT, DELIVERED)
        else:
            result = await supabase.rpc("update_order_status_simple", {
                "p_order_id": order_id,
                "p_order_type": order_type,
                "p_new_status": data.new_status.value,
                "p_triggered_by_user_id": triggered_by_user_id,
            }).execute()
            
            result_data = result.data
            
            if not result_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Order {order_id} ({order_type}) not found or update ignored."
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
                new_status=data.new_status.value
            )
            
            return result_data
    
    except Exception as e:
        logger.error(f"Order update failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# async def update_order_status(
#     order_id: str,
#     data: OrderStatusUpdate,
#     entity_type: str,
#     triggered_by_user_id: str,
#     table_name: str,
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ) -> dict:
#     """
#     Update order status with proper authorization and wallet handling.

#     Wallet changes:
#     - COMPLETED: Release escrow to vendor (customer confirms receipt)
#     - CANCELLED: Full refund to customer (if escrow still held)
#     - All others: No wallet change
#     """

#     # Fetch order with related data
#     order_resp = (
#         await supabase.table(table_name)
#         .select("*")
#         .eq("id", order_id)
#         .single()
#         .execute()
#     )
#     order = order_resp['data']
#     print(data.new_status)
#     print('*', * 100)
#     print(order)
#     print(type(order))
#     print(order['data'])
#     print('*', * 100)
#     print(order.data)
#     print('*', * 100)

#     customer_id = order["customer_id"]
#     vendor_id = order["vendor_id"]
#     current_status = order["order_status"]
#     amount_due_vendor = order['amount_due_vendor']


#     tranx_resp = (
#         await supabase.table("transactions")
#         .select("*")
#         .eq("order_id", order_id)
#         .execute()
#     )
#     tranx = tranx_resp.data[0]


#     print('*'*100)
#     print(tranx)
#     print(type(tranx))
#     print('*'*100)

#     # Authorization checks
#     if data.new_status in [
#         OrderStatus.PREPARING,
#         OrderStatus.READY,
#         OrderStatus.IN_TRANSIT,
#         OrderStatus.DELIVERED,
#     ]:
#         if triggered_by_user_id != vendor_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail=f"Only vendor can set status to {data.new_status}",
#             )

#     elif data.new_status == OrderStatus.COMPLETED:
#         if triggered_by_user_id != customer_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only customer can mark order as COMPLETED",
#             )

#     elif data.new_status == OrderStatus.CANCELLED:
#         if triggered_by_user_id not in [customer_id, vendor_id]:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only customer or vendor can cancel order",
#             )

#     # Prevent invalid transitions
#     if current_status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail=f"Cannot change status from {current_status}",
#         )

#     # Handle wallet changes
#     if data.new_status == OrderStatus.COMPLETED:
#         # Release escrow to vendor
#         if tranx['transaction_type'] != TransactionType.ESCROW_HOLD:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Cannot complete order - escrow not held",
#             )


#         # Deduct from customer escrow
#         await supabase.rpc(
#             "update_user_wallet",
#             {
#                 "p_user_id": str(customer_id),
#                 "p_balance_change": "0",
#                 "p_escrow_balance_change": f"-{grand_total}",
#             },
#         ).execute()

#         # Credit vendor wallet
#         await supabase.rpc(
#             "update_user_wallet",
#             {
#                 "p_user_id": str(order.vendor_id),
#                 "p_balance_change": f"{amount_due_vendor}",
#                 "p_escrow_balance_change": f"-{grand_total}",
#             },
#         ).execute()

#         # Update transaction record
#         # Update the transaction escrow status from ESCROW_HELD → ESCROW_RELEASED
#         await (
#             supabase.table("transactions")
#             .update(
#                 {
#                     "transaction_type": TransactionType.ESCROW_RELEASE,
#                 }
#             )
#             .eq("order_id", str(order_id))
#             .eq("transaction_type", "ESCROW_HOLD")
#             .execute()
#         )

#         # Update order
#         await (
#             supabase.table(table_name)
#             .update(
#                 {
#                     "order_status": OrderStatus.COMPLETED,
#                     "cancel_reason": data.cancel_reason,
#                 }
#             )
#             .eq("id", order_id)
#             .execute()
#         )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type=entity_type,
#             entity_id=str(order_id),
#             action="ORDER_COMPLETED",
#             old_value={
#                 "status": current_status,
#                 "transaction_type": tranx['transaction_type'],
#             },
#             new_value={"status": "COMPLETED", "escrow": "RELEASED"},
#             actor_id=str(triggered_by_user_id),
#             actor_type="USER",
#             change_amount=amount_due_vendor,
#             notes=f"Order completed by customer, escrow released to vendor",
#             request=request,
#         )

#         # Notify participants
#         await notify_user(
#             customer_id,
#             "Order Completed",
#             "Transaction completed",
#             data={"SUCCESS": "Transaction completed"},
#             supabase=supabase,
#         )

#         await notify_user(
#             vendor_id,
#             "Order Completed",
#             "Transaction completed",
#             data={"SUCCESS": "Transaction completed"},
#             supabase=supabase,
#         )

#         logger.info(
#             "food_order_completed",
#             order_id=order_id,
#             amount_released=str(amount_due_vendor),
#         )

#     elif data.new_status == OrderStatus.CANCELLED:
#         # Refund customer if escrow still held
#         if order.transaction_type == TransactionType.ESCROW_HOLD.value:
#             grand_total = Decimal(str(order["grand_total"]))

#             # Deduct from customer escrow and update balance
#             await supabase.rpc(
#                 "update_user_wallet",
#                 {
#                     "p_user_id": str(customer_id),
#                     "p_balance_change": f"{grand_total}",
#                     "p_escrow_balance_change": f"-{grand_total}",
#                 },
#             ).execute()

#             # Deduct from vendor wallet
#             await supabase.rpc(
#                 "update_user_wallet",
#                 {
#                     "p_user_id": str(vendor_id),
#                     "p_balance_change": "0",
#                     "p_escrow_balance_change": f"-{grand_total}",
#                 },
#             ).execute()

#             # Log refund transaction
#             await (
#                 supabase.table("transactions")
#                 .insert(
#                     {
#                         "amount": grand_total,
#                         "from_user_id": str(customer_id),
#                         "to_user_id": str(customer_id),
#                         "order_id": str(order_id),
#                         "wallet_id": (customer_id),
#                         "transaction_type": TransactionType.REFUNDED,
#                         "payment_status": "SUCCESS",
#                         "order_type": "FOOD",
#                         "details": {
#                             "label": "CREDIT",
#                             "reason": data.cancellation_reason or "ORDER_CANCELLED",
#                             "cancelled_by": "VENDOR"
#                             if triggered_by_user_id == vendor_id
#                             else "CUSTOMER",
#                         },
#                     }
#                 )
#                 .execute()
#             )

#             # Update order
#             await (
#                 supabase.table(table_name)
#                 .update(
#                     {
#                         "order_status": OrderStatus.CANCELLED,
#                         "payment_status": "REFUNDED",
#                     }
#                 )
#                 .eq("id", order_id)
#                 .execute()
#             )

#             # Audit log
#             await log_audit_event(
#                 supabase,
#                 entity_type=entity_type,
#                 entity_id=str(order_id),
#                 action="ORDER_CANCELLED",
#                 old_value={"status": current_status, "payment_status": "PAID"},
#                 new_value={"status": "CANCELLED", "payment_status": "REFUNDED"},
#                 actor_id=str(triggered_by_user_id),
#                 actor_type="USER",
#                 change_amount=grand_total,
#                 notes=data.cancellation_reason or "Order cancelled",
#                 request=request,
#             )

#             logger.info(
#                 "food_order_cancelled_refunded",
#                 order_id=order_id,
#                 refund_amount=str(grand_total),
#             )
#         else:
#             # Escrow already released - just update status
#             await (
#                 supabase.table(table_name)
#                 .update({"order_status": OrderStatus.CANCELLED})
#                 .eq("id", order_id)
#                 .execute()
#             )

#             logger.warning(
#                 "food_order_cancelled_no_refund",
#                 order_id=order_id,
#                 transaction_type=tranx['transaction_type'],
#             )

#     else:
#         # PREPARING, READY, IN_TRANSIT, DELIVERED - just status update
#         await (
#             supabase.table(table_name)
#             .update({"order_status": data.new_status})
#             .eq("id", order_id)
#             .execute()
#         )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type=entity_type,
#             entity_id=str(order_id),
#             action="STATUS_CHANGED",
#             old_value={"status": current_status},
#             new_value={"status": data.new_status},
#             actor_id=str(triggered_by_user_id),
#             actor_type="USER",
#             notes=f"Order status changed to {data.new_status}",
#             request=request,
#         )

#         logger.info(
#             "food_order_status_updated", order_id=order_id, new_status=data.new_status
#         )

#     return {"status": "success", "new_status": data.new_status}


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
    request: Request = None,
) -> dict:
    """Smart delivery status update with role-based authorization and wallet handling."""
    
    try:
        # Handle COMPLETED status
        if data.new_status == DeliveryStatus.COMPLETED:
            result = await supabase.rpc("mark_delivery_as_completed", {
                "p_delivery_id": delivery_id,
                "p_triggered_by_user_id": triggered_by_user_id,
            }).execute()
            
            result_data = result.data
            
        # Handle CANCELLED status
        elif data.new_status == DeliveryStatus.CANCELLED:
            result = await supabase.rpc("mark_delivery_as_cancelled", {
                "p_delivery_id": delivery_id,
                "p_triggered_by_user_id": triggered_by_user_id,
                "p_cancellation_reason": data.cancellation_reason,
            }).execute()
            
            result_data = result.data
            
        # Handle PICKED_UP (holds escrow)
        elif data.new_status == DeliveryStatus.PICKED_UP:
            result = await supabase.rpc("mark_delivery_as_picked_up", {
                "p_delivery_id": delivery_id,
                "p_triggered_by_user_id": triggered_by_user_id,
            }).execute()
            
            result_data = result.data
            
        # Handle DECLINED (special case - uses tx_ref)
        elif data.new_status == DeliveryStatus.DECLINED:
            # First get the delivery to get tx_ref and rider_id
            delivery_resp = await supabase.table("delivery_orders").select("*").eq("id", delivery_id).single().execute()
            delivery = delivery_resp.data
            
            # Get transaction
            tranx_resp = await supabase.table("transactions").select("*").eq("order_id", delivery_id).execute()
            tx_ref = tranx_resp.data[0]["tx_ref"] if tranx_resp.data else None
            
            if tx_ref:
                await supabase.rpc("decline_delivery", {
                    "p_tx_ref": tx_ref,
                    "p_rider_id": delivery["rider_id"],
                }).execute()
            
            # Update status
            await supabase.table("delivery_orders").update({
                "delivery_status": "DECLINED",
                "decline_reason": data.decline_reason,
            }).eq("id", delivery_id).execute()
            
            result_data = {
                "status": "success",
                "new_status": "DECLINED",
                "sender_id": delivery["sender_id"],
                "dispatch_id": delivery.get("dispatch_id"),
                "order_number": delivery["order_number"],
            }
            
        # Handle simple status updates (ASSIGNED, ACCEPTED, IN_TRANSIT, DELIVERED)
        else:
            result = await supabase.rpc("update_delivery_status_simple", {
                "p_delivery_id": delivery_id,
                "p_new_status": data.new_status.value,
                "p_triggered_by_user_id": triggered_by_user_id,
            }).execute()
            
            result_data = result.data
        
        # Send notifications
        await _send_delivery_notifications(
            order_number=result_data.get("order_number"),
            new_status=data.new_status,
            sender_id=result_data.get("sender_id"),
            rider_id=result_data.get("rider_id"),
            dispatch_id=result_data.get("dispatch_id"),
            cancellation_reason=data.cancellation_reason,
            decline_reason=data.decline_reason,
            cancelled_by_rider=result_data.get("cancelled_by") == "RIDER",
            supabase=supabase,
        )
        
        # Audit log
        await log_audit_event(
            supabase,
            entity_type="DELIVERY_ORDER",
            entity_id=delivery_id,
            action=f"STATUS_CHANGED_TO_{data.new_status.value}",
            old_value={"status": "previous"},
            new_value={"status": data.new_status.value},
            actor_id=triggered_by_user_id,
            actor_type="USER",
            notes=data.cancellation_reason or data.decline_reason or f"Delivery status changed to {data.new_status.value}",
            request=request,
        )
        
        logger.info("delivery_status_updated", delivery_id=delivery_id, new_status=data.new_status.value)
        
        return result_data
    
    except Exception as e:
        logger.error("delivery_status_update_failed", delivery_id=delivery_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update delivery status: {str(e)}")


# async def update_delivery_status(
#     delivery_id: str,
#     data: DeliveryStatusUpdate,
#     triggered_by_user_id: str,
#     supabase: AsyncClient,
#     request: Request = None,
# ) -> dict:
#     """
#     Smart delivery status update with role-based authorization and wallet handling.

#     Authorization:
#     - ASSIGNED: Sender only
#     - ACCEPTED/DECLINED: Rider only (after ASSIGNED)
#     - PICKED_UP, IN_TRANSIT, DELIVERED: Rider only (after ACCEPTED)
#     - COMPLETED: Sender only (after DELIVERED)
#     - CANCELLED: Sender or Rider (different handling based on status)

#     Wallet changes:
#     - ACCEPTED: Hold delivery_fee in sender's escrow
#     - COMPLETED: Release escrow to rider
#     - DECLINED: Refund sender, allow reassignment
#     - CANCELLED (before PICKED_UP): Full refund to sender
#     - CANCELLED (after PICKED_UP): Follow normal flow, pay rider on completion
#     - CANCELLED by rider: Refund sender + increment rider's cancel count
#     """

#     # Fetch delivery order
#     delivery_resp = (
#         await supabase.table("delivery_orders")
#         .select("*")
#         .eq("id", delivery_id)
#         .single()
#         .execute()
#     )
#     delivery = delivery_resp.data

#     if not delivery:
#         raise HTTPException(status_code=404, detail="Delivery order not found")

#     sender_id = delivery["sender_id"]
#     rider_id = delivery.get("rider_id")
#     dispatch_id = delivery.get("dispatch_id")
#     amount_due_dispatch = Decimal(str(delivery.get("amount_due_dispatch") or 0))
#     current_status = delivery["delivery_status"]
#     delivery_fee = Decimal(str(delivery["delivery_fee"]))

#     # Fetch transaction if exists
#     tranx_resp = (
#         await supabase.table("transactions")
#         .select("*")
#         .eq("order_id", delivery_id)
#         .execute()
#     )
#     tranx = tranx_resp.data[0] if tranx_resp.data else None
#     tx_ref = tranx.get("tx_ref")

#     # ===== AUTHORIZATION CHECKS =====

#     # Sender can: ASSIGN, COMPLETE, CANCEL
#     if data.new_status == DeliveryStatus.ASSIGNED:
#         if triggered_by_user_id != sender_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only sender can assign a rider",
#             )
#         # Allow reassignment after DECLINED or PENDING
#         if current_status not in [DeliveryStatus.PENDING, DeliveryStatus.DECLINED]:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Can only assign rider when status is PENDING or DECLINED, current: {current_status}",
#             )
#         if not rider_id:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="rider_id must be set before assigning",
#             )

#     # Rider can: ACCEPT, DECLINE (after ASSIGNED)
#     elif data.new_status in [DeliveryStatus.ACCEPTED, DeliveryStatus.DECLINED]:
#         if not rider_id or triggered_by_user_id != rider_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only assigned rider can accept/decline",
#             )
#         if current_status != DeliveryStatus.ASSIGNED:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Can only accept/decline when status is ASSIGNED, current: {current_status}",
#             )

#     # Rider can: PICK_UP (after ACCEPTED)
#     elif data.new_status == DeliveryStatus.PICKED_UP:
#         if not rider_id or triggered_by_user_id != rider_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only rider can mark as picked up",
#             )
#         if current_status != DeliveryStatus.ACCEPTED:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Can only pick up when status is ACCEPTED, current: {current_status}",
#             )

#     # Rider can: IN_TRANSIT (after PICKED_UP)
#     elif data.new_status == DeliveryStatus.IN_TRANSIT:
#         if not rider_id or triggered_by_user_id != rider_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only rider can mark as in transit",
#             )
#         if current_status != DeliveryStatus.PICKED_UP:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Can only go in transit after pickup, current: {current_status}",
#             )

#     # Rider can: DELIVERED (after IN_TRANSIT)
#     elif data.new_status == DeliveryStatus.DELIVERED:
#         if not rider_id or triggered_by_user_id != rider_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only rider can mark as delivered",
#             )
#         if current_status != DeliveryStatus.IN_TRANSIT:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Can only deliver when in transit, current: {current_status}",
#             )

#     # Sender can: COMPLETED (after DELIVERED)
#     elif data.new_status == DeliveryStatus.COMPLETED:
#         if triggered_by_user_id != sender_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only sender can mark as completed",
#             )
#         if current_status != DeliveryStatus.DELIVERED:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Can only complete when delivered, current: {current_status}",
#             )

#     # Both can: CANCEL (with different rules)
#     elif data.new_status == DeliveryStatus.CANCELLED:
#         if triggered_by_user_id not in [sender_id, rider_id]:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail="Only sender or rider can cancel",
#             )
#         if current_status in [DeliveryStatus.DELIVERED, DeliveryStatus.COMPLETED]:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Cannot cancel after delivery completion",
#             )

#     # Prevent invalid transitions (COMPLETED and CANCELLED are final, DECLINED allows reassignment)
#     if current_status == DeliveryStatus.COMPLETED:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Cannot change status - order already completed",
#         )

#     if (
#         current_status == DeliveryStatus.CANCELLED
#         and data.new_status != DeliveryStatus.ASSIGNED
#     ):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Cannot change status from CANCELLED (except to reassign)",
#         )

#     # ===== WALLET HANDLING =====

#     try:
#         # ACCEPTED: Hold delivery fee in sender's escrow
#         if data.new_status == DeliveryStatus.PICKED_UP:
#             # Check if payment already held
#             if tranx and tranx["transaction_type"] == "ESCROW_HOLD":
#                 logger.warning("delivery_escrow_already_held", delivery_id=delivery_id)
#             else:
#                 # Hold delivery fee in sender's escrow
#                 await supabase.rpc(
#                     "update_user_wallet",
#                     {
#                         "p_user_id": f"{sender_id}",
#                         "p_balance_change": str(-delivery_fee),
#                         "p_escrow_balance_change": str(delivery_fee),
#                     },
#                 ).execute()

#                 # Create escrow hold transaction
#                 await (
#                     supabase.table("transactions")
#                     .insert(
#                         {
#                             "amount": f"{delivery_fee}",
#                             "from_user_id": f"{sender_id}",
#                             "to_user_id": f"{rider_id}",
#                             "order_id": f"{delivery_id}",
#                             "wallet_id": f"{sender_id}",
#                             "transaction_type": "ESCROW_HOLD",
#                             "payment_status": "SUCCESS",
#                             "order_type": "DELIVERY",
#                             "details": {
#                                 "label": "DEBIT",
#                                 "status_trigger": "PICKED_UP",
#                             },
#                         }
#                     )
#                     .execute()
#                 )

#                 logger.info(
#                     "delivery_escrow_held",
#                     delivery_id=delivery_id,
#                     amount=str(delivery_fee),
#                 )

#         # COMPLETED: Release escrow to rider
#         elif data.new_status == DeliveryStatus.COMPLETED:
#             if not tranx or tranx["transaction_type"] != "ESCROW_HOLD":
#                 raise HTTPException(
#                     status_code=400, detail="Cannot complete - escrow not held"
#                 )

#             # Deduct from sender's escrow
#             await supabase.rpc(
#                 "update_user_wallet",
#                 {
#                     "p_user_id": sender_id,
#                     "p_balance_change": "0",
#                     "p_escrow_balance_change": f"-{delivery_fee}",
#                 },
#             ).execute()

#             # Credit rider's wallet
#             await supabase.rpc(
#                 "update_user_wallet",
#                 {
#                     "p_user_id": rider_id,
#                     "p_balance_change": str(amount_due_dispatch),
#                     "p_escrow_balance_change": f"{-delivery_fee}",
#                 },
#             ).execute()

#             # Update transaction to ESCROW_RELEASE
#             await (
#                 supabase.table("transactions")
#                 .update(
#                     {
#                         "transaction_type": "ESCROW_RELEASE",
#                     }
#                 )
#                 .eq("order_id", delivery_id)
#                 .eq("transaction_type", "ESCROW_HOLD")
#                 .execute()
#             )

#             #  Create escrow release transaction for dispatch
#             await (
#                 supabase.table("transactions")
#                 .insert(
#                     {
#                         "amount": f"{amount_due_dispatch}",
#                         "from_user_id": f"{sender_id}",
#                         "to_user_id": f"{dispatch_id}",
#                         "order_id": f"{delivery_id}",
#                         "wallet_id": f"{dispatch_id}",
#                         "transaction_type": "ESCROW_RELEASE",
#                         "payment_status": "SUCCESS",
#                         "order_type": "DELIVERY",
#                         "details": {"label": "CREDIT", "status_trigger": "COMPLETED"},
#                     }
#                 )
#                 .execute()
#             )

#             logger.info(
#                 "delivery_escrow_released",
#                 delivery_id=delivery_id,
#                 rider_id=rider_id,
#                 amount=str(delivery_fee),
#             )

#         # DECLINED: Refund sender and allow reassignment
#         elif data.new_status == DeliveryStatus.DECLINED:
#             if tranx and tranx["transaction_type"] == "ESCROW_HOLD":
#                 # Remove from sender's escrow and refund to balance
#                 await supabase.rpc(
#                     "update_user_wallet",
#                     {
#                         "p_user_id": f"{sender_id}",
#                         "p_balance_change": str(delivery_fee),
#                         "p_escrow_balance_change": f"-{delivery_fee}",
#                     },
#                 ).execute()

#                 # Create refund transaction
#                 await (
#                     supabase.table("transactions")
#                     .insert(
#                         {
#                             "amount": f'{delivery_fee}',
#                             "from_user_id": f"{sender_id}",
#                             "to_user_id": f"{sender_id}",
#                             "order_id": f"{delivery_id}",
#                             "wallet_id": f"{sender_id}",
#                             "transaction_type": "REFUNDED",
#                             "payment_status": "SUCCESS",
#                             "order_type": "DELIVERY",
#                             "details": {
#                                 "label": "CREDIT",
#                                 "reason": data.decline_reason or "DELIVERY_DECLINED",
#                                 "declined_by": "RIDER",
#                             },
#                         }
#                     )
#                     .execute()
#                 )

#                 logger.info(
#                     "delivery_refunded_after_decline",
#                     delivery_id=delivery_id,
#                     amount=str(delivery_fee),
#                 )

#         # CANCELLED: Different handling based on who cancelled and current status
#         elif data.new_status == DeliveryStatus.CANCELLED:
#             cancelled_by_rider = triggered_by_user_id == rider_id

#             # If cancelled by RIDER: Always refund sender and increment rider cancel count
#             if cancelled_by_rider:
#                 if tranx and tranx["transaction_type"] == "ESCROW_HOLD":
#                     # Remove from sender's escrow and refund to balance
#                     await supabase.rpc(
#                         "update_user_wallet",
#                         {
#                             "p_user_id": f"{sender_id}",
#                             "p_balance_change": str(delivery_fee),
#                             "p_escrow_balance_change": f"-{delivery_fee}",
#                         },
#                     ).execute()

#                     # Create refund transaction
#                     await (
#                         supabase.table("transactions")
#                         .insert(
#                             {
#                                 "amount": f'{delivery_fee}',
#                                 "from_user_id": f"{sender_id}",
#                                 "to_user_id": f"{sender_id}",
#                                 "order_id": f"{delivery_id}",
#                                 "wallet_id": f"{sender_id}",
#                                 "transaction_type": "REFUNDED",
#                                 "payment_status": "SUCCESS",
#                                 "order_type": "DELIVERY",
#                                 "details": {
#                                     "label": "CREDIT",
#                                     "reason": data.cancellation_reason
#                                     or "CANCELLED_BY_RIDER",
#                                     "cancelled_by": "RIDER",
#                                 },
#                             }
#                         )
#                         .execute()
#                     )

#                 # Increment rider's cancel count
#                 await supabase.rpc(
#                     "cancel_delivery_by_rider",
#                     {
#                         "p_order_id": f"{delivery_id}",
#                         "p_reason": data.cancellation_reason,
#                     },
#                 ).execute()

#                 logger.info(
#                     "delivery_cancelled_by_rider",
#                     delivery_id=delivery_id,
#                     rider_id=rider_id,
#                     refunded=str(delivery_fee),
#                 )

#             # If cancelled by SENDER
#             else:
#                 # Before PICKED_UP: Full refund
#                 if current_status in [
#                     DeliveryStatus.PENDING,
#                     DeliveryStatus.ASSIGNED,
#                     DeliveryStatus.ACCEPTED,
#                 ]:
#                     if tranx and tranx["transaction_type"] == "ESCROW_HOLD":
#                         # Remove from sender's escrow and refund to balance
#                         await supabase.rpc(
#                             "update_user_wallet",
#                             {
#                                 "p_user_id": f"{sender_id}",
#                                 "p_balance_change": str(delivery_fee),
#                                 "p_escrow_balance_change": f"-{delivery_fee}",
#                             },
#                         ).execute()

#                         # Create refund transaction
#                         await (
#                             supabase.table("transactions")
#                             .insert(
#                                 {
#                                     "amount": f"{delivery_fee}",
#                                     "from_user_id": f"{sender_id}",
#                                     "to_user_id": f"{sender_id}",
#                                     "order_id": delivery_id,
#                                     "wallet_id": f"{sender_id}",
#                                     "transaction_type": "REFUNDED",
#                                     "payment_status": "SUCCESS",
#                                     "order_type": "DELIVERY",
#                                     "details": {
#                                         "label": "CREDIT",
#                                         "reason": data.cancellation_reason
#                                         or "CANCELLED_BEFORE_PICKUP",
#                                         "cancelled_by": "SENDER",
#                                     },
#                                 }
#                             )
#                             .execute()
#                         )

#                         logger.info(
#                             "delivery_cancelled_before_pickup",
#                             delivery_id=delivery_id,
#                             refunded=str(delivery_fee),
#                         )

#                 # After PICKED_UP (IN_TRANSIT): Rider needs to return item, keep escrow held
#                 # Payment will be released when sender confirms return (marks as COMPLETED)
#                 elif current_status in [
#                     DeliveryStatus.PICKED_UP,
#                     DeliveryStatus.IN_TRANSIT,
#                 ]:
#                     # Just update status, escrow remains held
#                     # Rider will be paid when sender confirms item return
#                     logger.info(
#                         "delivery_cancelled_after_pickup",
#                         delivery_id=delivery_id,
#                         note="Escrow held for rider payment on return confirmation",
#                     )

#         # Update delivery status
#         update_data = {"delivery_status": data.new_status.value}

#         # Add reasons if provided
#         if data.new_status == DeliveryStatus.DECLINED and data.decline_reason:
#             update_data["decline_reason"] = data.decline_reason
#         if data.new_status == DeliveryStatus.CANCELLED and data.cancellation_reason:
#             update_data["cancellation_reason"] = data.cancellation_reason

#         # Clear rider_id on DECLINED to allow reassignment
#         if data.new_status == DeliveryStatus.DECLINED:
#             await supabase.rpc(
#                 "decline_delivery",
#                 {
#                     "p_tx_ref": f"{tx_ref}",
#                     "p_rider_id": f"{rider_id}",
#                 },
#             )

#             await notify_user(
#                 dispatch_id,
#                 "RIDER DECLINED",
#                 f"Rider declined order pickup please assign another rider.",
#                 data={"DECLINED": "Pickup Declined by rider"},
#                 supabase=supabase,
#             )

#         await (
#             supabase.table("delivery_orders")
#             .update(update_data)
#             .eq("id", delivery_id)
#             .execute()
#         )

#         # Send notifications
#         await _send_delivery_notifications(
#             order_number=f"{delivery['order_number']}",
#             new_status=data.new_status,
#             sender_id=sender_id,
#             rider_id=rider_id,
#             dispatch_id=dispatch_id,
#             cancellation_reason=data.cancellation_reason,
#             decline_reason=data.decline_reason,
#             cancelled_by_rider=(
#                 data.new_status == DeliveryStatus.CANCELLED
#                 and triggered_by_user_id == rider_id
#             ),
#             supabase=supabase,
#         )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type="DELIVERY_ORDER",
#             entity_id=delivery_id,
#             action=f"STATUS_CHANGED_TO_{data.new_status.value}",
#             old_value={"status": current_status},
#             new_value={"status": data.new_status.value},
#             actor_id=triggered_by_user_id,
#             actor_type="USER",
#             notes=data.cancellation_reason
#             or data.decline_reason
#             or f"Delivery status changed to {data.new_status.value}",
#             request=request,
#         )

#         logger.info(
#             "delivery_status_updated",
#             delivery_id=delivery_id,
#             new_status=data.new_status.value,
#         )

#         return {"status": "success", "new_status": data.new_status.value}

#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(
#             "delivery_status_update_failed",
#             delivery_id=delivery_id,
#             error=str(e),
#             exc_info=True,
#         )
#         raise HTTPException(
#             status_code=500, detail=f"Failed to update delivery status: {str(e)}"
#         )


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
