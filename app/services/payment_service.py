import json 
from app.utils.redis_utils import get_pending, delete_pending
from uuid import UUID
from supabase import AsyncClient
from app.utils.commission import get_commission_rate
from app.config.logging import logger
from app.utils.audit import log_audit_event
from typing import Optional
from fastapi import Request
from decimal import Decimal
from app.utils.payment import verify_transaction_tx_ref
from app.services.notification_service import notify_user


# ───────────────────────────────────────────────
# Delivery Payment
# ───────────────────────────────────────────────



async def process_successful_delivery_payment_rpc(
    tx_ref: str,
    paid_amount: Decimal,
    flw_ref: str,
    supabase: AsyncClient,
):
    """
    Process successful delivery payment.
    DB now handles ALL calculations - backend just passes data!
    """
    logger.info("processing_delivery_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # 1. Verify payment with Flutterwave
    verified = await verify_transaction_tx_ref(tx_ref)
    if not verified or verified.get("status") != "success":
        logger.error("delivery_payment_verification_failed", tx_ref=tx_ref)
        return {"status": "verification_failed"}

    # 2. Get pending data from Redis
    pending_key = f"pending_delivery_{tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        logger.warning("delivery_payment_pending_not_found", tx_ref=tx_ref)
        return {"status": "pending_not_found"}

    sender_id = str(pending["sender_id"])
    delivery_data = pending["delivery_data"]
    distance = Decimal(str(pending.get("distance", 0)))

    try:
        # Convert delivery_data to JSON string
        delivery_data_json = json.dumps(delivery_data) if isinstance(delivery_data, dict) else delivery_data
        
        logger.info(
            "calling_delivery_payment_rpc",
            tx_ref=tx_ref,
            sender_id=sender_id,
            delivery_data_type=type(delivery_data).__name__,
            delivery_data_json_type=type(delivery_data_json).__name__,
            distance=float(distance),
            data_json=delivery_data_json,
            data_raw=delivery_data
        )
        
        # 3. Call RPC - DB does ALL the work! 
        result = await supabase.rpc(
            "process_delivery_payment",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_paid_amount": str(paid_amount),
                "p_sender_id": sender_id,
                "p_delivery_data": delivery_data_json,
                "p_distance": str(distance),
            },
        ).execute()

        result_data = result.data
        
        # Already processed? Just cleanup and return
        if result_data.get("status") == "already_processed":
            logger.info(
                "delivery_payment_already_processed",
                tx_ref=tx_ref,
                order_id=result_data.get("order_id"),
            )
            await delete_pending(pending_key)
            return result_data

        # Success! Clean up Redis
        await delete_pending(pending_key)
        
        order_id = result_data["order_id"]
        
        logger.info(
            event="delivery_payment_processed_success",
            tx_ref=tx_ref,
            order_id=str(order_id),
            delivery_fee=result_data["delivery_fee"],
            platform_commission=result_data["platform_commission"],
        )
        
        # Send notification
        try:
            await notify_user(
                sender_id,
                "Payment Successful",
                f"Your delivery payment of ₦{result_data['delivery_fee']} has been received.",
                data={
                    "type": "DELIVERY_PAYMENT_SUCCESS",
                    "order_id": str(order_id),
                    "amount": str(result_data['delivery_fee']),
                },
                supabase=supabase,
            )
        except Exception as notif_error:
            logger.error("notification_failed", error=str(notif_error))
        
        return result_data

    except Exception as e:
        logger.error(
            event="delivery_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        raise


async def process_successful_delivery_payment(
    tx_ref: str,
    paid_amount: Decimal,
    flw_ref: str,
    supabase: AsyncClient,
):
    """
    Process successful delivery payment.
    Uses direct DB operations (like legacy code) for reliability.
    """
    logger.info("processing_delivery_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # 1. Verify payment
    verified = await verify_transaction_tx_ref(tx_ref)
    if not verified or verified.get("status") != "success":
        logger.error("delivery_payment_verification_failed", tx_ref=tx_ref)
        return {"status": "verification_failed"}

    # 2. Get pending data from Redis
    pending_key = f"pending_delivery_{tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        logger.warning("delivery_payment_pending_not_found", tx_ref=tx_ref)
        return {"status": "pending_not_found"}

    sender_id = str(pending["sender_id"])
    delivery_data = pending["delivery_data"]
    distance = Decimal(str(pending.get("distance", 0)))

    # 3. Check if already processed (idempotency)
    existing = await supabase.table("transactions").select("order_id").eq("tx_ref", tx_ref).execute()
    if existing.data:
        logger.info("delivery_payment_already_processed", tx_ref=tx_ref)
        await delete_pending(pending_key)
        return {
            "status": "already_processed",
            "order_id": existing.data[0]["order_id"],
        }

    try:
        # 4. Get charges from DB
        charges = await supabase.table("charges_and_commissions").select(
            "base_delivery_fee, delivery_fee_per_km, delivery_commission_rate"
        ).single().execute()

        if not charges.data:
            raise Exception("Charges configuration not found")

        base_fee = Decimal(str(charges.data["base_delivery_fee"]))
        per_km_fee = Decimal(str(charges.data["delivery_fee_per_km"]))
        commission_rate = Decimal(str(charges.data["delivery_commission_rate"]))

        # 5. Calculate fees
        delivery_fee = round(base_fee + (per_km_fee * distance), 2)
        amount_due_dispatch = round(delivery_fee * commission_rate, 2)
        platform_commission = delivery_fee - amount_due_dispatch

        # 6. Validate paid amount
        if round(paid_amount, 2) != delivery_fee:
            raise Exception(f"Amount mismatch: expected {delivery_fee}, got {paid_amount}")

        logger.info(
            "creating_delivery_order",
            sender_id=sender_id,
            delivery_fee=str(delivery_fee),
            amount_due_dispatch=str(amount_due_dispatch),
        )

        # 7. Create delivery order (just like legacy code!)
        order_resp = await supabase.table("delivery_orders").insert({
            "sender_id": sender_id,
            "package_name": delivery_data.get("package_name"),
            "receiver_phone": delivery_data.get("receiver_phone"),
            "pickup_location": delivery_data["pickup_location"],
            "destination": delivery_data["destination"],
            "pickup_coordinates": delivery_data["pickup_coordinates"],
            "dropoff_coordinates": delivery_data["dropoff_coordinates"],
            "additional_info": delivery_data.get("description"),
            "delivery_type": delivery_data.get("delivery_type", "STANDARD"),
            "total_price": str(delivery_fee),
            "amount_due_dispatch": str(amount_due_dispatch),
            "delivery_fee": str(delivery_fee),
            "duration": delivery_data.get("duration"),
            "delivery_status": "PENDING",
            "payment_status": "SUCCESS",
            "package_image_url": delivery_data.get("package_image_url"),
            "distance": str(distance),
            "tx_ref": tx_ref,
            "flw_ref": flw_ref,
            "order_type": "DELIVERY",
            # "sender_phone_number": ("receiver_phone"),
        }).execute()

        order_id = order_resp.data[0]["id"]
        logger.info("delivery_order_created", order_id=order_id)

        # 8. Credit sender wallet (DEPOSIT)
        await supabase.rpc("update_user_wallet", {
            "p_user_id": sender_id,
            "p_balance_change": str(delivery_fee),
            "p_escrow_balance_change": "0",
        }).execute()

        logger.info("sender_wallet_credited", sender_id=sender_id, amount=str(delivery_fee))

        # 9. Create DEPOSIT transaction
        await supabase.table("transactions").insert({
            "tx_ref": tx_ref,
            "amount": float(delivery_fee),
            "from_user_id": sender_id,
            "to_user_id": sender_id,
            "order_id": order_id,
            "wallet_id": sender_id,
            "transaction_type": "DEPOSIT",
            "payment_status": "SUCCESS",
            "payment_method": "FLUTTERWAVE",
            "order_type": "DELIVERY",
            "details": {
                "flw_ref": flw_ref,
                "label": "CREDIT",
                "note": "Delivery payment received from Flutterwave",
                "delivery_fee_breakdown": {
                    "base_fee": float(base_fee),
                    "per_km_fee": float(per_km_fee),
                    "distance_km": float(distance),
                    "total_fee": float(delivery_fee),
                    "dispatch_gets": float(amount_due_dispatch),
                    "platform_commission": float(platform_commission),
                }
            }
        }).execute()

        logger.info("deposit_transaction_created", tx_ref=tx_ref)

        # 10. Clean up Redis
        await delete_pending(pending_key)
        logger.info("pending_delivery_deleted", tx_ref=tx_ref)

        # 11. Send notification
        try:
            await notify_user(
                sender_id,
                "Payment Successful",
                f"Your delivery payment of ₦{delivery_fee} has been received.",
                data={
                    "type": "DELIVERY_PAYMENT_SUCCESS",
                    "order_id": order_id,
                    "amount": str(delivery_fee),
                },
                supabase=supabase,
            )
        except Exception as notif_error:
            logger.error("notification_failed", error=str(notif_error))

        logger.info(
            event="delivery_payment_processed_success",
            tx_ref=tx_ref,
            order_id=order_id,
            delivery_fee=str(delivery_fee),
            platform_commission=str(platform_commission),
        )

        return {
            "status": "success",
            "order_id": order_id,
            "tx_ref": tx_ref,
            "delivery_fee": float(delivery_fee),
            "amount_due_dispatch": float(amount_due_dispatch),
            "platform_commission": float(platform_commission),
            "message": "Delivery payment processed successfully",
        }

    except Exception as e:
        logger.error(
            event="delivery_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        raise

# async def process_successful_delivery_payment(
#     tx_ref: str,
#     paid_amount: Decimal,
#     flw_ref: str,
#     supabase: AsyncClient,
# ):
#     """
#     Process successful delivery payment using atomic database transaction
#     """
#     logger.info("processing_delivery_payment", tx_ref=tx_ref, paid_amount=paid_amount)

#     # Verify payment
#     verified = await verify_transaction_tx_ref(tx_ref)
#     if not verified or verified.get("status") != "success":
#         logger.error("delivery_payment_verification_failed", tx_ref=tx_ref)
#         return

#     # Get pending data from Redis
#     pending_key = f"pending_delivery_{tx_ref}"
#     pending = await get_pending(pending_key)

#     if not pending:
#         logger.warning("delivery_payment_pending_not_found", tx_ref=tx_ref)
#         return

#     expected_fee = pending["delivery_fee"]
#     sender_id = str(pending["sender_id"])
#     delivery_data = pending["delivery_data"]
#     amount_due_dispatch = pending["amount_due_dispatch"]

#     # Validate amounts
#     expected_rounded = abs(Decimal(str(expected_fee)).quantize(Decimal("0.00")))
#     paid_rounded = Decimal(str(paid_amount)).quantize(Decimal("0.00"))

#     if paid_rounded != expected_rounded:
#         logger.warning(
#             event="delivery_payment_amount_mismatch",
#             tx_ref=tx_ref,
#             expected=expected_rounded,
#             paid=paid_rounded,
#         )
#         await delete_pending(pending_key)
#         return

#     try:
#         # Create delivery_order (no rider yet)
#         logger.info(
#             "creating_delivery_order", sender_id=sender_id, delivery_data=delivery_data
#         )

#         order_resp = (
#             await supabase.table("delivery_orders")
#             .insert(
#                 {
#                     "sender_id": sender_id,
#                     "package_name": delivery_data.get("package_name"),
#                     "receiver_phone": delivery_data.get("receiver_phone"),
#                     "pickup_location": delivery_data["pickup_location"],
#                     "destination": delivery_data["destination"],
#                     "pickup_coordinates": delivery_data["pickup_coordinates"],
#                     "dropoff_coordinates": delivery_data["dropoff_coordinates"],
#                     "additional_info": delivery_data.get("description"),
#                     "delivery_type": delivery_data["delivery_type"],
#                     "total_price": float(expected_rounded),
#                     "amount_due_dispatch": float(amount_due_dispatch),
#                     "delivery_fee": float(expected_rounded),
#                     "duration": delivery_data.get("duration"),
#                     "delivery_status": "PAID_NEEDS_RIDER",
#                     "payment_status": "PAID",
#                     "escrow_status": "HELD",
#                     "package_image_url": delivery_data.get("package_image_url"),
#                     "distance": float(pending.get("distance", 0)),
#                     "tx_ref": tx_ref,
#                     "flw_ref": flw_ref,
#                     "order_type": "DELIVERY",
#                 }
#             )
#             .execute()
#         )

#         order_id = order_resp.data[0]["id"]
#         logger.info("delivery_order_created", order_id=order_id)

#         # Hold fee in sender escrow
#         logger.info(
#             "holding_fee_in_sender_escrow",
#             sender_id=sender_id,
#             expected_fee=expected_fee,
#         )
#         await supabase.rpc(
#             "update_user_wallet",
#             {
#                 "p_user_id": str(sender_id),
#                 "p_balance_change": f"{expected_rounded}",
#                 "p_escrow_balance_change": "0",
#             },
#         ).execute()
#         logger.info(
#             "fee_held_in_sender_escrow", sender_id=sender_id, expected_fee=expected_fee
#         )

#         # Create transaction
#         logger.info(
#             "creating_transaction",
#             tx_ref=tx_ref,
#             sender_id=sender_id,
#             expected_fee=expected_fee,
#         )
#         await (
#             supabase.table("transactions")
#             .insert(
#                 {
#                     "tx_ref": tx_ref,
#                     "amount": float(expected_rounded),
#                     "from_user_id": str(sender_id),
#                     "order_id": str(order_id),
#                     "wallet_id": str(sender_id),
#                     "transaction_type": "ESCROW_HOLD",
#                     "payment_status": "SUCCESS",
#                     "payment_method": "FLUTTERWAVE",
#                     "order_type": "DELIVERY",
#                     "details": {"flw_ref": flw_ref},
#                 }
#             )
#             .execute()
#         )

#         # Delete from Redis after successful DB transaction
#         await delete_pending(pending_key)
#         logger.info("pending_delivery_deleted", tx_ref=tx_ref)

#         logger.info(
#             event="delivery_payment_processed_success",
#             tx_ref=tx_ref,
#             order_id=str(order_id),
#         )

#     except Exception as e:
#         logger.error(
#             event="delivery_payment_processing_error",
#             tx_ref=tx_ref,
#             error=str(e),
#             exc_info=True,
#         )
#         raise


# ───────────────────────────────────────────────
# Food Payment
# ───────────────────────────────────────────────
async def process_successful_food_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
):
    """Process successful food order payment using atomic RPC."""
    logger.info("processing_food_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # Verify payment
    verified = await verify_transaction_tx_ref(tx_ref)
    if not verified or verified.get("status") != "success":
        logger.error("food_payment_verification_failed", tx_ref=tx_ref)
        return

    # Get pending data
    pending_key = f"pending_food_{tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        logger.warning("food_payment_pending_not_found", tx_ref=tx_ref)
        return

    try:
        # Call atomic RPC
        result = await supabase.rpc("process_food_payment", {
            "p_tx_ref": tx_ref,
            "p_flw_ref": flw_ref,
            "p_paid_amount": float(paid_amount),
            "p_customer_id": pending["customer_id"],
            "p_vendor_id": pending["vendor_id"],
            "p_order_data": pending["items"],
            "p_total_price": float(Decimal(pending["total_price"])),
            "p_delivery_fee": float(Decimal(pending.get("delivery_fee", 0))),
            "p_grand_total": float(Decimal(pending["grand_total"])),
            "p_delivery_option": pending["delivery_option"],
            "p_additional_info": pending.get("additional_info"),
            "p_customer_name": pending.get("name", "Customer"),
        }).execute()

        result_data = result.data

        if result_data.get("status") == "already_processed":
            logger.info("food_payment_already_processed", tx_ref=tx_ref)
            await delete_pending(pending_key)
            return result_data

        # Success! Cleanup Redis
        await delete_pending(pending_key)
        
        order_id = result_data["order_id"]
        
        # Notify vendor
        await notify_user(
            user_id=result_data["vendor_id"],
            title="New Order",
            body=f"You have a new order from {pending.get('name', 'Customer')}",
            data={"order_id": str(order_id), "type": "FOOD_PAYMENT"},
            supabase=supabase,
        )
        
        # Audit log
        await log_audit_event(
            supabase,
            entity_type="FOOD_ORDER",
            entity_id=str(order_id),
            action="PAYMENT_RECEIVED",
            new_value={"payment_status": "PAID", "amount": result_data["grand_total"]},
            actor_id=result_data["customer_id"],
            actor_type="USER",
            change_amount=Decimal(str(result_data["grand_total"])),
            notes=f"Food order payment received via Flutterwave: {tx_ref}",
            request=request,
        )
        
        logger.info("food_payment_processed_success", tx_ref=tx_ref, order_id=str(order_id))
        
        return result_data

    except Exception as e:
        logger.error("food_payment_processing_error", tx_ref=tx_ref, error=str(e), exc_info=True)
        raise
# async def process_successful_food_payment(
#     tx_ref: str,
#     paid_amount: float,
#     flw_ref: str,
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ):
#     """
#     Webhook handler for successful food order payment.
#     - Fetches pending state from Redis
#     - Validates amount
#     - Creates food_orders + food_order_items
#     - Holds full amount in customer escrow (via RPC)
#     - Creates transaction record (HELD)
#     - Cleans up Redis
#     """
#     logger.info("processing_food_payment", tx_ref=tx_ref, paid_amount=paid_amount)

#     verified = await verify_transaction_tx_ref(tx_ref)
#     if not verified or verified.get("status") != "success":
#         logger.error(event="delivery_payment_verification_failed", tx_ref=tx_ref)
#         return

#     pending_key = f"pending_food_{tx_ref}"
#     pending = await get_pending(pending_key)

#     if not pending:
#         logger.warning(event="food_payment_pending_not_found", tx_ref=tx_ref)
#         return None

#     expected_total = Decimal(pending["grand_total"])
#     customer_id = pending["customer_id"]
#     vendor_id = pending["vendor_id"]
#     delivery_fee = Decimal(pending.get("delivery_fee", 0))
#     order_data = pending["items"]
#     name = pending.get("name")
#     total_price = Decimal(str(pending["total_price"]))
#     delivery_option = pending["delivery_option"]
#     additional_info = pending.get("additional_info")

#     # Idempotency + amount validation
#     existing_tx = (
#         await supabase.table("transactions").select("id").eq("tx_ref", tx_ref).execute()
#     )

#     if existing_tx.data:
#         logger.warning(event="food_payment_already_processed", tx_ref=tx_ref)
#         await delete_pending(pending_key)
#         return {"status": "already_processed"}

#     expected_rounded = Decimal(str(expected_total)).quantize(Decimal("0.00"))
#     paid_rounded = Decimal(str(paid_amount)).quantize(Decimal("0.00"))

#     if paid_rounded != expected_rounded:
#         logger.warning(
#             event="food_payment_amount_mismatch",
#             tx_ref=tx_ref,
#             expected=expected_rounded,
#             paid=paid_rounded,
#         )
#         await delete_pending(pending_key)
#         # Optional: log mismatch or trigger refund
#         return {"status": "amount_mismatch"}

#     try:
#         # Get dynamic commission rate for FOOD
#         commission_rate = Decimal(str(await get_commission_rate("FOOD", supabase)))

#         # Calculate what vendor should receive (grand_total - commission)
#         amount_due_vendor = expected_total * (1 - commission_rate)

#         # 1. Create food_order record
#         order_resp = (
#             await supabase.table("food_orders")
#             .insert(
#                 {
#                     "customer_id": customer_id,
#                     "vendor_id": vendor_id,
#                     "total_price": str(total_price),
#                     "delivery_fee": str(delivery_fee),
#                     "grand_total": str(expected_total),
#                     "amount_due_vendor": str(amount_due_vendor),
#                     "additional_info": additional_info,
#                     "delivery_option": delivery_option,
#                     "order_status": "PENDING",
#                     "payment_status": "SUCCESS",
#                     "order_type": "FOOD",
#                     "tx_ref": f"{tx_ref}",
#                 }
#             )
#             .execute()
#         )

#         order_id = order_resp.data[0]["id"]

#         # 2. Create food_order_items (multiple rows)
#         for item in order_data:
#             await (
#                 supabase.table("food_order_items")
#                 .insert(
#                     {
#                         "order_id": order_id,
#                         "item_id": item["item_id"],
#                         "quantity": item["quantity"],
#                         "sizes": item.get("sizes", []),
#                         "sides": item.get("sides", []),
#                         "images": item.get("images", []),
#                     }
#                 )
#                 .execute()
#             )

#         # 3. Hold full amount in customer escrow (positive delta)
#         await supabase.rpc(
#             "update_user_wallet",
#             {
#                 "p_user_id": customer_id,
#                 "p_balance_change": "0",
#                 "p_escrow_balance_change": expected_total,
#             },
#         ).execute()

#         await supabase.rpc(
#             "update_user_wallet",
#             {
#                 "p_user_id": vendor_id,
#                 "p_balance_change": "0",
#                 "p_escrow_balance_change": expected_total,
#             },
#         ).execute()

#         # 4. Create transaction record (HELD)
#         await (
#             supabase.table("transactions")
#             .insert(
#                 {
#                     "tx_ref": tx_ref,
#                     "amount": str(expected_total),
#                     "from_user_id": customer_id,
#                     "to_user_id": vendor_id,
#                     "order_id": order_id,
#                     "wallet_id": customer_id,
#                     "transaction_type": "ESCROW_HOLD",
#                     "payment_status": "SUCCESS",
#                     "payment_method": "FLUTTERWAVE",
#                     "order_type": "FOOD",
#                     "details": {
#                         "flw_ref": flw_ref,
#                         "label": "DEBIT",
#                         "order_type": "FOOD",
#                     },
#                 }
#             )
#             .execute()
#         )

#         await (
#             supabase.table("transactions")
#             .insert(
#                 {
#                     "tx_ref": tx_ref,
#                     "amount": str(expected_total),
#                     "from_user_id": customer_id,
#                     "to_user_id": vendor_id,
#                     "order_id": order_id,
#                     "wallet_id": vendor_id,
#                     "transaction_type": "ESCROW_HOLD",
#                     "payment_status": "SUCCESS",
#                     "payment_method": "FLUTTERWAVE",
#                     "order_type": "FOOD",
#                     "details": {
#                         "flw_ref": flw_ref,
#                         "label": "CREDIT",
#                         "from": f"{name}",
#                         "order_type": "FOOD",
#                     },
#                 }
#             )
#             .execute()
#         )

#         # Notify rider on success
#         await notify_user(
#             user_id=vendor_id,
#             title="New Order",
#             body=f"You have a new order from {name}",
#             data={"order_id": str(order_id), "type": "FOOD_PAYMENT"},
#             supabase=supabase,
#         )

#         # 5. Cleanup Redis
#         await delete_pending(pending_key)

#         logger.info(
#             event="food_payment_processed_success",
#             tx_ref=tx_ref,
#             order_id=str(order_id),
#         )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type="FOOD_ORDER",
#             entity_id=str(order_id),
#             action="PAYMENT_RECEIVED",
#             new_value={"payment_status": "PAID", "amount": expected_total},
#             actor_id=customer_id,
#             actor_type="USER",
#             change_amount=Decimal(str(expected_total)),
#             notes=f"Food order payment received via Flutterwave: {tx_ref}",
#             request=request,
#         )

#         # Log platform commission
#         await (
#             supabase.table("platform_commissions")
#             .insert(
#                 {
#                     "to_user_id": vendor_id,
#                     "from_user_id": customer_id,
#                     "order_id": str(order_id),
#                     "service_type": "FOOD",
#                     "description": f"Platform commission from food order {order_id} (₦{amount_due_vendor})",
#                 }
#             )
#             .execute()
#         )

#         return {"status": "success", "order_id": str(order_id)}

#     except Exception as e:
#         # Critical: attempt refund on error (implement refund_flutterwave if needed)
#         logger.error(
#             event="food_payment_processing_error",
#             tx_ref=tx_ref,
#             error=str(e),
#             exc_info=True,
#         )
#         await delete_pending(pending_key)
#         # Optional: await refund_flutterwave(tx_ref)
#         raise


# ───────────────────────────────────────────────
# Top-up Payment
# ───────────────────────────────────────────────
async def process_successful_topup_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
):
    """Process successful wallet top-up payment using atomic RPC."""
    logger.info("processing_topup_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # Verify payment
    verified = await verify_transaction_tx_ref(tx_ref)
    if not verified or verified.get("status") != "success":
        logger.error("topup_payment_verification_failed", tx_ref=tx_ref)
        return

    # Get pending data
    pending_key = f"pending_topup_{tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        logger.warning("topup_payment_pending_not_found", tx_ref=tx_ref)
        return

    expected_amount = Decimal(str(pending["amount"]))
    user_id = pending["user_id"]

    # Validate amount
    expected_rounded = expected_amount.quantize(Decimal("0.00"))
    paid_rounded = Decimal(str(paid_amount)).quantize(Decimal("0.00"))

    if paid_rounded != expected_rounded:
        logger.warning(
            "topup_payment_amount_mismatch",
            tx_ref=tx_ref,
            expected=expected_rounded,
            paid=paid_rounded,
        )
        await delete_pending(pending_key)
        return

    try:
        # Call atomic RPC - everything happens in one transaction!
        result = await supabase.rpc("process_topup_payment", {
            "p_tx_ref": tx_ref,
            "p_flw_ref": flw_ref,
            "p_paid_amount": float(paid_rounded),
            "p_user_id": user_id,
        }).execute()

        result_data = result.data

        if result_data.get("status") == "already_processed":
            logger.info("topup_payment_already_processed", tx_ref=tx_ref)
            await delete_pending(pending_key)
            return result_data

        # Success! Cleanup Redis
        await delete_pending(pending_key)
        
        # Notify user
        await notify_user(
            user_id=user_id,
            title="Wallet Top-up Successful",
            body=f"₦{paid_rounded} has been added to your wallet",
            data={
                "user_id": str(user_id), 
                "type": "WALLET_TOPUP",
                "amount": str(paid_rounded),
                "new_balance": str(result_data["new_balance"])
            },
            supabase=supabase,
        )
        
        # Audit log
        await log_audit_event(
            supabase,
            entity_type="WALLET",
            entity_id=user_id,
            action="TOP_UP",
            old_value={"balance": float(result_data["old_balance"])},
            new_value={"balance": float(result_data["new_balance"])},
            change_amount=Decimal(str(paid_rounded)),
            actor_id=user_id,
            actor_type="USER",
            notes=f"Wallet top-up of ₦{paid_rounded} via Flutterwave",
            request=request,
        )
        
        logger.info(
            "topup_payment_processed_success",
            tx_ref=tx_ref,
            user_id=user_id,
            amount=float(paid_rounded),
            new_balance=float(result_data["new_balance"]),
        )
        
        return result_data

    except Exception as e:
        logger.error(
            "topup_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        raise
# async def process_successful_topup_payment(
#     tx_ref: str,
#     paid_amount: float,
#     flw_ref: str,
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ):
#     logger.info("processing_topup_payment", tx_ref=tx_ref, paid_amount=paid_amount)

#     verified = await verify_transaction_tx_ref(tx_ref)
#     if not verified or verified.get("status") != "success":
#         logger.error(event="delivery_payment_verification_failed", tx_ref=tx_ref)
#         return
#     pending_key = f"pending_topup_{tx_ref}"
#     pending = await get_pending(pending_key)

#     if not pending:
#         logger.warning(event="topup_payment_pending_not_found", tx_ref=tx_ref)
#         return  # already processed

#     expected_amount = pending["amount"]
#     user_id = pending["user_id"]

#     expected_rounded = Decimal(str(expected_amount)).quantize(Decimal("0.00"))
#     paid_rounded = Decimal(str(paid_amount)).quantize(Decimal("0.00"))

#     if paid_rounded != expected_rounded:
#         logger.warning(
#             event="topup_payment_amount_mismatch",
#             tx_ref=tx_ref,
#             expected=expected_rounded,
#             paid=paid_rounded,
#         )
#         await delete_pending(pending_key)
#         return

#     try:
#         # Get current balance for audit
#         wallet_resp = (
#             await supabase.table("wallets")
#             .select("balance")
#             .eq("user_id", user_id)
#             .single()
#             .execute()
#         )

#         old_balance = (
#             Decimal(str(wallet_resp.data["balance"]))
#             if wallet_resp.data
#             else Decimal("0")
#         )

#         # Add funds to wallet balance (atomic RPC)
#         await supabase.rpc(
#             "update_user_wallet",
#             {
#                 "p_user_id": user_id,
#                 "p_balance_change": paid_amount,
#                 "p_escrow_balance_change": "0",
#             },
#         ).execute()

#         # Get new balance
#         wallet_resp_after = (
#             await supabase.table("wallets")
#             .select("balance")
#             .eq("user_id", user_id)
#             .single()
#             .execute()
#         )

#         new_balance = Decimal(str(wallet_resp_after.data["balance"]))

#         # Record transaction
#         await (
#             supabase.table("transactions")
#             .insert(
#                 {
#                     "tx_ref": tx_ref,
#                     "amount": paid_amount,
#                     "from_user_id": user_id,
#                     "to_user_id": user_id,
#                     "wallet_id": user_id,
#                     "transaction_type": "DEPOSIT",
#                     "payment_method": "FLUTTERWAVE",
#                     "order_type": "DEPOSIT",
#                     "details": {"flw_ref": flw_ref, "label": "CREDIT"},
#                 }
#             )
#             .execute()
#         )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type="WALLET",
#             entity_id=user_id,
#             action="TOP_UP",
#             old_value={"balance": float(old_balance)},
#             new_value={"balance": float(new_balance)},
#             change_amount=Decimal(str(paid_amount)),
#             actor_id=user_id,
#             actor_type="USER",
#             notes=f"Top-up of {paid_amount} via Flutterwave",
#             request=request,
#         )

#         # Notify rider on success
#         await notify_user(
#             user_id=user_id,
#             title="Wallet Top up",
#             body=f"Wallet top up successful",
#             data={"user_id": str(user_id), "type": "WALLET TOP UP"},
#             supabase=supabase,
#         )

#         await delete_pending(pending_key)
#         logger.info(
#             "topup_payment_processed_success",
#             tx_ref=tx_ref,
#             user_id=user_id,
#             amount=paid_amount,
#         )

#     except Exception as e:
#         logger.error(
#             event="topup_payment_processing_error",
#             tx_ref=tx_ref,
#             error=str(e),
#             exc_info=True,
#         )
#         await delete_pending(pending_key)
#         raise


# ───────────────────────────────────────────────
# Product Payment
# ───────────────────────────────────────────────


async def process_successful_product_payment(
    tx_ref: str, paid_amount: float, flw_ref: str, supabase: AsyncClient
):
    logger.info(
        event="processing_product_payment", tx_ref=tx_ref, paid_amount=paid_amount
    )

    verified = await verify_transaction_tx_ref(tx_ref)
    if not verified or verified.get("status") != "success":
        logger.error(event="delivery_payment_verification_failed", tx_ref=tx_ref)
        return

    pending_key = f"pending_product_{tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        logger.warning(event="pending_order_not_found", tx_ref=tx_ref)
        return

    expected_total = Decimal(pending["grand_total"])
    customer_id = pending["customer_id"]
    vendor_id = pending["vendor_id"]
    product_id = pending["item_id"]  # item_id refers to product_id
    quantity = int(pending["quantity"])

    # Idempotency check
    existing = (
        await supabase.table("transactions").select("id").eq("tx_ref", tx_ref).execute()
    )

    if existing.data:
        await delete_pending(pending_key)
        return

    expected_rounded = Decimal(str(expected_total)).quantize(Decimal("0.00"))
    paid_rounded = Decimal(str(paid_amount)).quantize(Decimal("0.00"))

    if paid_rounded != expected_rounded:
        logger.error(
            event="payment_amount_mismatch",
            tx_ref=tx_ref,
            expected=str(expected_rounded),
            paid=str(paid_rounded),
        )
        await delete_pending(pending_key)
        return

    try:
        # 1 Create the main product_order
        product_id = pending["item_id"]
        quantity = int(pending["quantity"])
        product_name = pending.get("product_name", "Product")
        unit_price = pending.get("price", 0)

        # 2. Create the main product_order
        order_resp = (
            await supabase.table("product_orders")
            .insert(
                {
                    "tx_ref": tx_ref,
                    "customer_id": pending["customer_id"],
                    "vendor_id": pending["vendor_id"],
                    "grand_total": pending["grand_total"],
                    "amount_due_vendor": pending["subtotal"],
                    "shipping_cost": pending.get("shipping_cost", 0),
                    "delivery_option": pending["delivery_option"],
                    "delivery_address": pending["delivery_address"],
                    "additional_info": pending["additional_info"],
                    "order_status": "PENDING",
                    "payment_status": "PAID",
                    "escrow_status": "HELD",
                    "order_type": "PRODUCT",
                }
            )
            .execute()
        )

        order_id = order_resp.data[0]["id"]

        await (
            supabase.table("product_order_items")
            .insert(
                {
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "name": product_name,
                    "images": pending.get("images", None),
                    "price": unit_price,
                    "selected_size": pending.get("selected_size", None),
                    "selected_color": pending.get("selected_color", None),
                }
            )
            .execute()
        )

        # Update buyer escrow balance
        await supabase.rpc(
            "update_user_wallet",
            {
                "p_user_id": customer_id,
                "p_balance_change": "0",
                "p_escrow_balance_change": expected_total,
            },
        ).execute()

        # Create transaction record
        await (
            supabase.table("transactions")
            .insert(
                {
                    "tx_ref": tx_ref,
                    "amount": expected_total,
                    "from_user_id": customer_id,
                    "to_user_id": vendor_id,
                    "wallet_id": customer_id,
                    "order_id": order_id,
                    "transaction_type": "ESCROW_HOLD",
                    "payment_method": "FLUTTERWAVE",
                    "order_type": "PRODUCT",
                    "details": {"flw_ref": flw_ref, "label": "DEBIT"},
                }
            )
            .execute()
        )

        # Notify rider on success
        await notify_user(
            user_id=vendor_id,
            title="New Order",
            body=f"You have a new order",
            data={"order_id": str(order_id), "type": "PRODUCT_PAYMENT"},
            supabase=supabase,
        )

        await delete_pending(pending_key)

    except Exception as e:
        logger.error(
            event="product_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        # Depending on your failure strategy, you might not want to delete pending here
        # so it can be retried, but keeping it as per your original logic.
        await delete_pending(pending_key)
        raise

async def process_successful_laundry_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
):
    """Process successful laundry order payment using atomic RPC."""
    logger.info("processing_laundry_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # Verify payment
    verified = await verify_transaction_tx_ref(tx_ref)
    if not verified or verified.get("status") != "success":
        logger.error("laundry_payment_verification_failed", tx_ref=tx_ref)
        return

    # Get pending data
    pending_key = f"pending_laundry_{tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        logger.warning("laundry_payment_pending_not_found", tx_ref=tx_ref)
        return

    try:
        # Call atomic RPC
        result = await supabase.rpc("process_laundry_payment", {
            "p_tx_ref": tx_ref,
            "p_flw_ref": flw_ref,
            "p_paid_amount": float(paid_amount),
            "p_customer_id": pending["customer_id"],
            "p_vendor_id": pending["vendor_id"],
            "p_subtotal": float(Decimal(pending["total_price"])),
            "p_delivery_fee": float(Decimal(pending.get("delivery_fee", 0))),
            "p_grand_total": float(Decimal(pending["grand_total"])),
            "p_delivery_option": pending.get("delivery_option", "PICKUP"),
            "p_additional_info": pending.get("additional_info"),
            "p_customer_name": pending.get("name", "Customer"),
        }).execute()

        result_data = result.data

        if result_data.get("status") == "already_processed":
            logger.info("laundry_payment_already_processed", tx_ref=tx_ref)
            await delete_pending(pending_key)
            return result_data

        # Success! Cleanup Redis
        await delete_pending(pending_key)
        
        order_id = result_data["order_id"]
        
        # Notify vendor
        await notify_user(
            user_id=result_data["vendor_id"],
            title="New Laundry Order",
            body="You have a new laundry order",
            data={"order_id": str(order_id), "type": "LAUNDRY_PAYMENT"},
            supabase=supabase,
        )
        
        # Audit log
        await log_audit_event(
            supabase,
            entity_type="LAUNDRY_ORDER",
            entity_id=str(order_id),
            action="PAYMENT_RECEIVED",
            new_value={"payment_status": "PAID", "amount": result_data["grand_total"]},
            actor_id=result_data["customer_id"],
            actor_type="USER",
            change_amount=Decimal(str(result_data["grand_total"])),
            notes=f"Laundry payment received via Flutterwave: {tx_ref}",
            request=request,
        )
        
        logger.info("laundry_payment_processed_success", tx_ref=tx_ref, order_id=str(order_id))
        
        return result_data

    except Exception as e:
        logger.error("laundry_payment_processing_error", tx_ref=tx_ref, error=str(e), exc_info=True)
        raise

# async def process_successful_laundry_payment(
#     tx_ref: str,
#     paid_amount: float,
#     flw_ref: str,
#     supabase: AsyncClient,
#     request: Optional[Request] = None,
# ):
#     """
#     Handle successful payment for laundry order (webhook callback).
#     - Creates laundry_orders record
#     - Holds full amount in customer escrow
#     - Calculates amount_due_vendor (vendor gets subtotal - commission)
#     - Logs platform commission
#     - Creates transaction record
#     """
#     logger.info(
#         event="processing_laundry_payment", tx_ref=tx_ref, paid_amount=paid_amount
#     )

#     verified = await verify_transaction_tx_ref(tx_ref)
#     if not verified or verified.get("status") != "success":
#         logger.error(event="delivery_payment_verification_failed", tx_ref=tx_ref)
#         return

#     pending_key = f"pending_laundry_{tx_ref}"
#     pending = await get_pending(pending_key)

#     if not pending:
#         logger.warning(event="laundry_payment_pending_not_found", tx_ref=tx_ref)
#         return  # already processed or expired

#     expected_total = pending["grand_total"]
#     customer_id = pending["customer_id"]
#     vendor_id = pending["vendor_id"]
#     subtotal = pending["total_price"]
#     delivery_fee = pending.get("delivery_fee", 0)

#     expected_rounded = Decimal(str(expected_total)).quantize(Decimal("0.00"))
#     paid_rounded = Decimal(str(paid_amount)).quantize(Decimal("0.00"))

#     if paid_rounded != expected_rounded:
#         logger.warning(
#             event="laundry_payment_amount_mismatch",
#             tx_ref=tx_ref,
#             expected=expected_rounded,
#             paid=paid_rounded,
#         )
#         await delete_pending(pending_key)
#         return

#     try:
#         # Get dynamic commission rate for LAUNDRY
#         commission_rate = await get_commission_rate("LAUNDRY", supabase)

#         # Calculate vendor share (usually on subtotal only)
#         amount_due_vendor = expected_total * (1 - Decimal(str(commission_rate)))

#         # Platform commission amount (for logging)
#         commission_amount = expected_total - amount_due_vendor

#         # Create laundry_orders record
#         order_resp = (
#             await supabase.table("laundry_orders")
#             .insert(
#                 {
#                     "customer_id": customer_id,
#                     "vendor_id": vendor_id,
#                     "subtotal": subtotal,
#                     "delivery_fee": delivery_fee,
#                     "total_price": subtotal,
#                     "grand_total": expected_total,
#                     "additional_info": pending.get("additional_info"),
#                     "delivery_option": pending.get("delivery_option"),
#                     "order_status": "PENDING",
#                     "payment_status": "PAID",
#                     "escrow_status": "HELD",
#                     "amount_due_vendor": amount_due_vendor,
#                     "order_type": "LAUNDRY",
#                     "tx_ref": f"{tx_ref}",
#                 }
#             )
#             .execute()
#         )

#         order_id = order_resp.data[0]["id"]

#         # Hold full amount in customer escrow
#         await supabase.rpc(
#             "update_user_wallet",
#             {
#                 "p_user_id": customer_id,
#                 "p_balance_change": str(0),
#                 "p_escrow_balance_change": expected_total,
#             },
#         ).execute()

#         # Create transaction record
#         await (
#             supabase.table("transactions")
#             .insert(
#                 {
#                     "tx_ref": tx_ref,
#                     "amount": expected_total,
#                     "from_user_id": customer_id,
#                     "to_user_id": vendor_id,  # or null if held in escrow
#                     "order_id": order_id,
#                     "wallet_id": customer_id,
#                     "transaction_type": "ESCROW_HOLD",
#                     "payment_method": "FLUTTERWAVE",
#                     "order_type": "LAUNDRY",
#                     "details": {"flw_ref": flw_ref, "label": "DEBIT"},
#                 }
#             )
#             .execute()
#         )

#         # Log platform commission
#         await (
#             supabase.table("platform_commissions")
#             .insert(
#                 {
#                     "to_user_id": vendor_id,
#                     "from_user_id": customer_id,
#                     "order_id": str(order_id),
#                     "service_type": "LAUNDRY",
#                     "description": f"Platform commission from laundry order {order_id} (₦{amount_due_vendor})",
#                 }
#             )
#             .execute()
#         )

#         # Notify rider on success
#         await notify_user(
#             user_id=vendor_id,
#             title="New Order",
#             body=f"You have a new order",
#             data={"order_id": str(order_id), "type": "LAUNDRY_PAYMENT"},
#             supabase=supabase,
#         )

#         await delete_pending(pending_key)

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type="LAUNDRY_ORDER",
#             entity_id=str(order_id),
#             action="PAYMENT_RECEIVED",
#             new_value={"payment_status": "PAID", "amount": expected_total},
#             actor_id=customer_id,
#             actor_type="USER",
#             change_amount=Decimal(str(expected_total)),
#             notes=f"Laundry payment received via Flutterwave: {tx_ref}",
#             request=request,
#         )

#         logger.info(
#             event="laundry_payment_processed_success",
#             tx_ref=tx_ref,
#             order_id=str(order_id),
#         )

#     except Exception as e:
#         logger.error(
#             event="laundry_payment_processing_error",
#             tx_ref=tx_ref,
#             error=str(e),
#             exc_info=True,
#         )
#         await delete_pending(pending_key)
#         raise
