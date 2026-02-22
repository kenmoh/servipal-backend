import json
from typing import Literal
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


def parse_coordinates(value):
    """Ensure coordinates are a list [lat, lng], not a string."""
    if isinstance(value, str):
        return json.loads(value)  # "[6.5, 3.3]" → [6.5, 3.3]
    return value 

# ───────────────────────────────────────────────
# Delivery Payment
# ───────────────────────────────────────────────


async def process_successful_delivery_payment_rpc(
    tx_ref: str,
    paid_amount: float,
    payment_method: Literal["CARD", "WALLET"],
    flw_ref: str,
    supabase: AsyncClient,
):
    logger.info(
        event="processing_delivery_payment",
        tx_ref=tx_ref,
        paid_amount=paid_amount,
    )


    if payment_method == "CARD":
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            logger.error("delivery_payment_verification_failed", tx_ref=tx_ref)
            return {"status": "verification_failed"}

    # 1. Get pending data from Redis
    pending_key = f"pending_delivery_{tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        logger.warning(event="pending_delivery_not_found", tx_ref=tx_ref)
        return

    try:
        delivery_data = pending["delivery_data"]
        distance = Decimal(str(pending.get("distance", 0)))
        sender_id = str(pending["sender_id"])

        # 2. Call RPC (fee recalculated inside RPC from distance — source of truth)
        result = await supabase.rpc(
            "process_delivery_payment",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_sender_id": sender_id,
                "p_paid_amount": str(paid_amount),
                "p_distance": str(distance),
                "p_package_name": delivery_data.get("package_name"),
                "p_receiver_phone": delivery_data.get("receiver_phone"),
                "p_sender_phone_number": delivery_data.get("sender_phone_number"),
                "p_pickup_location": delivery_data["pickup_location"],
                "p_destination": delivery_data["destination"],
                "p_pickup_coordinates": parse_coordinates(delivery_data["pickup_coordinates"]),
                "p_dropoff_coordinates": parse_coordinates(delivery_data["dropoff_coordinates"]),
                "p_additional_info": delivery_data.get("description"),
                "p_delivery_type": delivery_data.get("delivery_type", "STANDARD"),
                "p_duration": delivery_data.get("duration"),
                "p_package_image_url": delivery_data.get("package_image_url"),
            },
        ).execute()

        response = result.data

        if response.get("status") == "already_processed":
            logger.info(
                event="delivery_payment_already_processed",
                tx_ref=tx_ref,
                order_id=response.get("order_id"),
            )
            await delete_pending(pending_key)
            return

        logger.info(
            event="delivery_payment_success",
            tx_ref=tx_ref,
            order_id=response.get("order_id"),
            delivery_fee=response.get("delivery_fee"),
            platform_commission=response.get("platform_commission"),
        )

        # 3. Notify sender
        await notify_user(
            user_id=sender_id,
            title="Payment Successful",
            body=f"Your delivery payment of ₦{response.get('delivery_fee')} has been received.",
            data={
                "type": "DELIVERY_PAYMENT_SUCCESS",
                "order_id": str(response.get("order_id")),
                "amount": str(response.get("delivery_fee")),
            },
            supabase=supabase,
        )

        await delete_pending(pending_key)

    except Exception as e:
        logger.error(
            event="delivery_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        await delete_pending(pending_key)
        raise



async def process_successful_delivery_payment(
    tx_ref: str,
    paid_amount: Decimal,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "WALLET"],
):
    """
    Process successful delivery payment.
    Uses direct DB operations (like legacy code) for reliability.
    """
    logger.info("processing_delivery_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # 1. Verify payment
    if payment_method == "CARD":
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            logger.error("delivery_payment_verification_failed", tx_ref=tx_ref)
            return {"status": "verification_failed"}

    if payment_method == "WALLET":
        existing = (
        await supabase.table("wallet_payment")
        .select("id, status, amount")
        .eq("tx_ref", tx_ref)
        .single()
        .execute()
    )

        if existing.data:
            logger.info(
                event="wallet_payment_already_processed", level="info", tx_ref=tx_ref
            )
            return {
                "status": existing.data["status"],
                "tx_ref": existing.data["tx_ref"],
                "amount": existing.data["amount"],
                "message": "Wallet payment already initiated",
            }

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
    existing = (
        await supabase.table("transactions")
        .select("order_id")
        .eq("tx_ref", tx_ref)
        .execute()
    )
    if existing.data:
        logger.info("delivery_payment_already_processed", tx_ref=tx_ref)
        await delete_pending(pending_key)
        return {
            "status": "already_processed",
            "order_id": existing.data[0]["order_id"],
        }

    try:
        # 4. Get charges from DB
        charges = (
            await supabase.table("charges_and_commissions")
            .select("base_delivery_fee, delivery_fee_per_km, delivery_commission_rate")
            .single()
            .execute()
        )

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
            raise Exception(
                f"Amount mismatch: expected {delivery_fee}, got {paid_amount}"
            )

        logger.info(
            "creating_delivery_order",
            sender_id=sender_id,
            delivery_fee=str(delivery_fee),
            amount_due_dispatch=str(amount_due_dispatch),
        )

        # 7. Create delivery order (just like legacy code!)
        order_resp = (
            await supabase.table("delivery_orders")
            .insert(
                {
                    "sender_id": sender_id,
                    "package_name": delivery_data.get("package_name"),
                    "receiver_phone": delivery_data.get("receiver_phone"),
                    "sender_phone_number": delivery_data.get("sender_phone_number"),
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
                    "payment_status": "PAID",
                    "package_image_url": delivery_data.get("package_image_url"),
                    "distance": str(distance),
                    "tx_ref": tx_ref,
                    "flw_ref": flw_ref,
                    "order_type": "DELIVERY",
                    # "sender_phone_number": ("receiver_phone"),
                }
            )
            .execute()
        )

        order_id = order_resp.data[0]["id"]
        logger.info("delivery_order_created", order_id=order_id)

        # 8. Credit sender wallet (DEPOSIT)
        await supabase.rpc(
            "update_user_wallet",
            {
                "p_user_id": sender_id,
                "p_balance_change": str(delivery_fee),
                "p_escrow_balance_change": "0",
            },
        ).execute()

        logger.info(
            "sender_wallet_credited", sender_id=sender_id, amount=str(delivery_fee)
        )

        # 9. Create DEPOSIT transaction
        await (
            supabase.table("transactions")
            .insert(
                {
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
                            "base_fee": str(base_fee),
                            "per_km_fee": str(per_km_fee),
                            "distance_km": str(distance),
                            "total_fee": str(delivery_fee),
                            "dispatch_gets": str(amount_due_dispatch),
                            "platform_commission": str(platform_commission),
                        },
                    },
                }
            )
            .execute()
        )

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
            "delivery_fee": str(delivery_fee),
            "amount_due_dispatch": str(amount_due_dispatch),
            "platform_commission": str(platform_commission),
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
        result = await supabase.rpc(
            "process_food_payment",
            {
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
                "p_destination": pending.get("delivery_address", None),
            },
        ).execute()

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

        logger.info(
            "food_payment_processed_success", tx_ref=tx_ref, order_id=str(order_id)
        )

        return result_data

    except Exception as e:
        logger.error(
            "food_payment_processing_error", tx_ref=tx_ref, error=str(e), exc_info=True
        )
        raise


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
        result = await supabase.rpc(
            "process_topup_payment",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_paid_amount": str(paid_rounded),
                "p_user_id": user_id,
            },
        ).execute()

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
                "new_balance": str(result_data["new_balance"]),
            },
            supabase=supabase,
        )

        # Audit log
        await log_audit_event(
            supabase,
            entity_type="WALLET",
            entity_id=user_id,
            action="TOP_UP",
            old_value={"balance": str(result_data["old_balance"])},
            new_value={"balance": str(result_data["new_balance"])},
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


# ───────────────────────────────────────────────
# Product Payment
# ───────────────────────────────────────────────

# services/product_payment.py

from decimal import Decimal
from supabase import AsyncClient
import structlog

logger = structlog.get_logger()


async def process_successful_product_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
):
    logger.info(
        event="processing_product_payment",
        tx_ref=tx_ref,
        paid_amount=paid_amount,
    )

    verified = await verify_transaction_tx_ref(tx_ref)
    if not verified or verified.get("status") != "success":
        logger.error(event="delivery_payment_verification_failed", tx_ref=tx_ref)
        return

    # 1. Get pending data from Redis
    pending_key = f"pending_product_{tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        logger.warning(event="pending_order_not_found", tx_ref=tx_ref)
        return

    try:
        grand_total = Decimal(str(pending["grand_total"]))
        paid_rounded = Decimal(str(paid_amount)).quantize(Decimal("0.00"))
        expected_rounded = grand_total.quantize(Decimal("0.00"))

        # 2. Amount validation
        if paid_rounded != expected_rounded:
            logger.error(
                event="product_payment_amount_mismatch",
                tx_ref=tx_ref,
                expected=str(expected_rounded),
                paid=str(paid_rounded),
            )
            await delete_pending(pending_key)
            return

        # 3. Call RPC
        result = await supabase.rpc(
            "process_product_payment",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_customer_id": pending["customer_id"],
                "p_vendor_id": pending["vendor_id"],
                "p_product_id": pending["item_id"],
                "p_quantity": int(pending["quantity"]),
                "p_product_name": pending.get("product_name", "Product"),
                "p_unit_price": float(pending.get("price", 0)),
                "p_subtotal": float(pending["subtotal"]),
                "p_shipping_cost": float(pending.get("shipping_cost", 0)),
                "p_grand_total": float(grand_total),
                "p_paid_amount": float(paid_rounded),
                "p_delivery_option": pending["delivery_option"],
                "p_delivery_address": pending["delivery_address"],
                "p_additional_info": pending.get("additional_info"),
                "p_images": pending.get("images"),
                "p_selected_size": pending.get("selected_size"),
                "p_selected_color": pending.get("selected_color"),
            },
        ).execute()

        response = result.data

        if response.get("status") == "already_processed":
            logger.info(
                event="product_payment_already_processed",
                tx_ref=tx_ref,
                order_id=response.get("order_id"),
            )
            await delete_pending(pending_key)
            return

        logger.info(
            event="product_payment_success",
            tx_ref=tx_ref,
            order_id=response.get("order_id"),
            grand_total=str(grand_total),
        )

        # 4. Notify vendor
        await notify_user(
            user_id=pending["vendor_id"],
            title="New Order",
            body="You have a new product order",
            data={
                "order_id": str(response.get("order_id")),
                "type": "PRODUCT_PAYMENT",
            },
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
        await delete_pending(pending_key)
        raise


async def process_successful_product_payment_non_rpc(
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
                    "payment_status": "SUCCESS",
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
        result = await supabase.rpc(
            "process_laundry_payment",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_paid_amount": str(paid_amount),
                "p_customer_id": pending["customer_id"],
                "p_vendor_id": pending["vendor_id"],
                "p_order_data": pending["items"],
                "p_subtotal": str(Decimal(pending["subtotal"])),
                "p_delivery_fee": str(Decimal(pending.get("delivery_fee", 0))),
                "p_grand_total": str(Decimal(pending["grand_total"])),
                "p_delivery_option": pending.get("delivery_option", "PICKUP"),
                "p_additional_info": pending.get("additional_info"),
                "p_customer_name": pending.get("name", "Customer"),
                "p_destination": pending.get("delivery_address", None),
            },
        ).execute()

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

        logger.info(
            "laundry_payment_processed_success", tx_ref=tx_ref, order_id=str(order_id)
        )

        return result_data

    except Exception as e:
        logger.error(
            "laundry_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        raise
