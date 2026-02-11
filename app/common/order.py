from uuid import UUID
from typing import Optional
from decimal import Decimal
from supabase import AsyncClient
from fastapi import HTTPException, status, Request
from enum import Enum
from app.config.logging import logger
from app.utils.audit import log_audit_event
from pydantic import BaseModel

class OrderStatus(str, Enum):
    PENDING = 'PENDING' 
    PREPARING = 'PREPARING' 
    READY = 'READY'
    COMPLETED ='COMPLETED'
    CANCELLED = 'CANCELLED'
    IN_TRANSIT = 'IN_TRANSIT'
    DELIVERED = 'DELIVERED'

class TransactionType(str, Enum):
    DEPOSIT = 'DEPOSIT'
    WITHDRAWAL = 'RWITHDRAWAL'
    ESCROW_RELEASE = 'ESCROW_RELEASE'
    ESCROW_HOLD = 'ESCROW_HOLD'
    REFUNDED = 'REFUNDED'

class OrderUpdateResponse(BaseModel):
    status: str = "success"
    new_status: OrderStatus
   
   

async def update_order_status(
    order_id: str,
    entity_type: str,
    new_status: OrderStatus,
    triggered_by_user_id: str,
    table_name: str,
    supabase: AsyncClient,
    cancellation_reason: Optional[str] = None,
    request: Optional[Request] = None,
)-> OrderUpdateResponse:
    """
    Update order status with proper authorization and wallet handling.
    
    Wallet changes:
    - COMPLETED: Release escrow to vendor (customer confirms receipt)
    - CANCELLED: Full refund to customer (if escrow still held)
    - All others: No wallet change
    """
    
    # Fetch order with related data
    order_resp = await supabase.table(table_name).select("*").eq("id", order_id).single().execute()
    order = order_resp.data
    
    customer_id = order["customer_id"]
    vendor_id = order["vendor_id"]
    current_status = order["order_status"]
    
    tranx_resp = await supabase.table("transactions").select("*").eq("order_id", order_id).execute()
    tranx = tranx_resp.data
    
    # Authorization checks
    if new_status in [OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED]:
        if triggered_by_user_id != vendor_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail= f"Only vendor can set status to {new_status}")
    
    elif new_status == OrderStatus.COMPLETED:
        if triggered_by_user_id != customer_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only customer can mark order as COMPLETED")
    
    elif new_status == OrderStatus.CANCELLED:
        if triggered_by_user_id not in [customer_id, vendor_id]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only customer or vendor can cancel order")
    
    # Prevent invalid transitions
    if current_status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Cannot change status from {current_status}")
    
    # Handle wallet changes
    if new_status == OrderStatus.COMPLETED:
        # Release escrow to vendor
        if tranx.transaction_type != TransactionType.ESCROW_HOLD.value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot complete order - escrow not held")
        
        grand_total = Decimal(str(order["grand_total"]))
        amount_due_vendor = Decimal(str(order["amount_due_vendor"]))
        
        # Deduct from customer escrow
        await supabase.rpc("update_user_wallet", {
            "p_user_id": str(order.customer_id),
            "p_balance_change": '0',
            "p_escrow_balance_change": f"-{order.grand_total}",
        }).execute()


        # Credit vendor wallet
        await supabase.rpc("update_user_wallet", {
            "p_user_id": str(order.vendor_id),
            "p_balance_change": f'{order.amount_due_vendor}',
            "p_escrow_balance_change": f"-{order.grand_total}",
        }).execute()
        
       
        
        # Update transaction record
        # Update the transaction escrow status from ESCROW_HELD → ESCROW_RELEASED
        await supabase.table("transactions").update({
            "transaction_type": TransactionType.ESCROW_RELEASE.value,
        }).eq("order_id", str(order_id)).eq("transaction_type", "ESCROW_HOLD").execute()
        
        # Update order
        await supabase.table(table_name).update({
            "order_status": OrderStatus.COMPLETED.value,
        }).eq("id", order_id).execute()
        
        # Audit log
        await log_audit_event(
            supabase,
            entity_type=entity_type,
            entity_id=order_id,
            action="ORDER_COMPLETED",
            old_value={"status": current_status, "transaction_type": tranx.transaction_type},
            new_value={"status": "COMPLETED", "escrow": "RELEASED"},
            actor_id=triggered_by_user_id,
            actor_type="USER",
            change_amount=amount_due_vendor,
            notes=f"Order completed by customer, escrow released to vendor",
            request=request,
        )
        
        logger.info("food_order_completed", order_id=order_id, amount_released=str(amount_due_vendor))
    
    elif new_status == OrderStatus.CANCELLED:
        # Refund customer if escrow still held
        if order.transaction_type == TransactionType.ESCROW_HOLD.value:
            grand_total = Decimal(str(order["grand_total"]))
            
             # Deduct from customer escrow and update balance
            await supabase.rpc("update_user_wallet", {
                "p_user_id": str(order.customer_id),
                "p_balance_change": f'{order.grand_total}',
                "p_escrow_balance_change": f"-{order.grand_total}",
            }).execute()


            # Deduct from vendor wallet
            await supabase.rpc("update_user_wallet", {
                "p_user_id": str(order.vendor_id),
                "p_balance_change": '0',
                "p_escrow_balance_change": f"-{order.grand_total}",
            }).execute()
            
            # Log refund transaction
            await supabase.table("transactions").insert({
                "amount": grand_total,
                "from_user_id": customer_id,
                "to_user_id": customer_id,
                "order_id": order_id,
                "wallet_id": customer_id,
                "transaction_type": TransactionType.REFUNDED.value,
                "payment_status": "SUCCESS",
                "order_type": "FOOD",
                "details": {
                    "label": "CREDIT",
                    "reason": cancellation_reason or "ORDER_CANCELLED",
                    "cancelled_by": "VENDOR" if triggered_by_user_id == vendor_id else "CUSTOMER"
                }
            }).execute()
            
            # Update order
            await supabase.table(table_name).update({
                "order_status": OrderStatus.CANCELLED.value,
                "payment_status": 'REFUNDED',
               
            }).eq("id", order_id).execute()
            
            # Audit log
            await log_audit_event(
                supabase,
                entity_type=entity_type,
                entity_id=order_id,
                action="ORDER_CANCELLED",
                old_value={"status": current_status, "payment_status": "PAID"},
                new_value={"status": "CANCELLED", "payment_status": "REFUNDED"},
                actor_id=triggered_by_user_id,
                actor_type="USER",
                change_amount=grand_total,
                notes=cancellation_reason or "Order cancelled",
                request=request,
            )
            
            logger.info("food_order_cancelled_refunded", order_id=order_id, refund_amount=str(grand_total))
        else:
            # Escrow already released - just update status
            await supabase.table("food_orders").update({
                "order_status": OrderStatus.CANCELLED.value
            }).eq("id", order_id).execute()
            
            logger.warning("food_order_cancelled_no_refund", order_id=order_id, transaction_type=tranx.transaction_type)
    
    else:
        # PREPARING, READY, IN_TRANSIT, DELIVERED - just status update
        await supabase.table("food_orders").update({
            "order_status": new_status
        }).eq("id", order_id).execute()
        
        # Audit log
        await log_audit_event(
            supabase,
            entity_type=entity_type,
            entity_id=order_id,
            action="STATUS_CHANGED",
            old_value={"status": current_status},
            new_value={"status": new_status},
            actor_id=triggered_by_user_id,
            actor_type="USER",
            notes=f"Order status changed to {new_status}",
            request=request,
        )
        
        logger.info("food_order_status_updated", order_id=order_id, new_status=new_status)
    
    return {"status": "success", "new_status": new_status}