import json
import json
from typing import Literal
from datetime import datetime, timezone
from app.utils.redis_utils import get_pending, delete_pending
from uuid import UUID
from supabase import AsyncClient, Client
from app.config.logging import logger
from app.utils.audit import log_audit_event
from typing import Optional
from fastapi import HTTPException, Request, status
from decimal import Decimal
from app.utils.payment import verify_transaction_tx_ref
from app.services.notification_service import notify_user
from app.services.delivery_service import extract_rpc_data
from postgrest.exceptions import APIError


# def parse_coordinates(value):
#     """Ensure coordinates are a list [lat, lng], not a string."""
#     if isinstance(value, str):
#         return json.loads(value)  # "[6.5, 3.3]" → [6.5, 3.3]
#     return value


# ───────────────────────────────────────────────
# Delivery Payment
# ───────────────────────────────────────────────


# async def process_successful_delivery_payment(
#     tx_ref: str,
#     paid_amount: Decimal,
#     flw_ref: str,
#     supabase: AsyncClient,
#     payment_method: Literal["CARD", "WALLET", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
#     pending_data: dict = None,
# ):
#     logger.info(
#         "processing_delivery_payment",
#         tx_ref=tx_ref,
#         paid_amount=paid_amount,
#         payment_method=payment_method,
#     )

#     # 1. Verify — CARD and BANK_TRANSFER
#     if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
#         logger.info(
#             "verifying_transaction", tx_ref=tx_ref, payment_method=payment_method
#         )

#         verified = await verify_transaction_tx_ref(tx_ref)

#         # Log verification result
#         logger.info(
#             "verification_result",
#             tx_ref=tx_ref,
#             verified_status=verified.get("status") if verified else None,
#             verified_data=verified,
#         )

#         if not verified or verified.get("status") != "success":
#             logger.error(
#                 "delivery_payment_verification_failed",
#                 tx_ref=tx_ref,
#                 verified=verified,
#                 payment_method=payment_method,
#             )
#             return {"status": "verification_failed"}

#     # 2. Get pending data
#     pending_key = f"pending_delivery_{tx_ref}"
#     if payment_method in {"WALLET", "PAY_ON_DELIVERY"} and pending_data:
#         pending = pending_data
#     else:
#         pending = await get_pending(pending_key)

#     if not pending:
#         logger.warning("delivery_payment_pending_not_found", tx_ref=tx_ref)
#         return {"status": "pending_not_found"}

#     sender_id = str(pending["sender_id"])
#     delivery_data = pending["delivery_data"]
#     distance = Decimal(str(pending.get("distance", 0)))

#     # Parse coordinates — may be list or string depending on source
#     pickup_coordinates = parse_coordinates(delivery_data["pickup_coordinates"])
#     dropoff_coordinates = parse_coordinates(delivery_data["dropoff_coordinates"])

#     try:
#         result_data = None
#         try:
#             result = await supabase.rpc(
#                 "process_delivery_payment",
#                 {
#                     "p_tx_ref": tx_ref,
#                     "p_flw_ref": flw_ref,
#                     "p_sender_id": sender_id,
#                     "p_paid_amount": str(paid_amount),
#                     "p_distance": str(distance),
#                     "p_package_name": delivery_data.get("package_name"),
#                     "p_receiver_phone": delivery_data.get("receiver_phone"),
#                     "p_sender_phone_number": delivery_data.get("sender_phone_number"),
#                     "p_pickup_location": delivery_data["pickup_location"],
#                     "p_destination": delivery_data["destination"],
#                     "p_pickup_coordinates": pickup_coordinates,
#                     "p_dropoff_coordinates": dropoff_coordinates,
#                     "p_additional_info": delivery_data.get("description"),
#                     "p_delivery_type": delivery_data.get("delivery_type", "STANDARD"),
#                     "p_duration": delivery_data.get("duration"),
#                     "p_package_image_url": delivery_data.get("package_image_url"),
#                     "p_payment_method": payment_method,
#                 },
#             ).execute()
#             result_data = result.data

#         except APIError as e:
#             result_data = extract_rpc_data(e)
#             if not result_data:
#                 raise

#         if not result_data:
#             raise Exception("No data returned from RPC")

#         if result_data.get("status") == "already_processed":
#             logger.info("delivery_payment_already_processed", tx_ref=tx_ref)
#             await delete_pending(pending_key)
#             return result_data

#         order_id = result_data["order_id"]
#         delivery_fee = Decimal(str(result_data["delivery_fee"]))

#         await delete_pending(pending_key)

#         try:
#             await notify_user(
#                 sender_id,
#                 "Payment Successful",
#                 f"Your delivery payments of ₦{delivery_fee} has been received.",
#                 data={
#                     "type": "DELIVERY_PAYMENT_SUCCESS",
#                     "order_id": order_id,
#                     "amount": str(delivery_fee),
#                 },
#                 supabase=supabase,
#             )
#         except Exception as e:
#             logger.error("notification_failed", error=str(e))

#         logger.info(
#             "delivery_payment_processed_success",
#             tx_ref=tx_ref,
#             order_id=order_id,
#             payment_method=payment_method,
#         )

#         return result_data

#     except APIError as e:
#         result_data = extract_rpc_data(e)
#         if not result_data:
#             logger.error(
#                 "delivery_payment_processing_error",
#                 tx_ref=tx_ref,
#                 error=str(result_data),
#                 exc_info=True,
#             )
#             raise

#     except Exception as e:
#         logger.error(
#             "delivery_payment_processing_error",
#             tx_ref=tx_ref,
#             error=str(e),
#             exc_info=True,
#         )
#         raise


async def process_successful_delivery_payment(
    tx_ref: str,
    paid_amount: Decimal,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
):
    logger.info(
        "processing_delivery_payment",
        tx_ref=tx_ref,
        paid_amount=paid_amount,
        payment_method=payment_method,
    )

    # 1. Verify payment (for external methods)
    if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
        verified = await verify_transaction_tx_ref(tx_ref)

        if not verified or verified.get("status") != "success":
            logger.error("delivery_payment_verification_failed", tx_ref=tx_ref)
            return {"status": "verification_failed"}

    # 2. FETCH INTENT (SOURCE OF TRUTH)
    intent_res = await supabase.table("transaction_intents") \
        .select("*") \
        .eq("tx_ref", tx_ref) \
        .single() \
        .execute()

    if not intent_res.data:
        logger.error("intent_not_found", tx_ref=tx_ref)
        return {"status": "intent_not_found"}

    intent = intent_res.data
    payload = intent["payload"]

    # 3. IDEMPOTENCY CHECK
    if intent["status"] == "COMPLETED":
        logger.info("delivery_already_processed", tx_ref=tx_ref)
        return {"status": "already_processed"}

    # 4. Expiry check
    if intent.get("expires_at"):
        if datetime.fromisoformat(intent["expires_at"]) < datetime.now(timezone.utc):
            return {"status": "expired"}


    # 5. EXTRACT DATA FROM PAYLOAD
    delivery = payload.get("delivery", {})
    package = payload.get("package", {})
    pricing = payload.get("pricing", {})

    if float(intent["amount"]) != float(pricing.get("total")):
        raise Exception("Amount mismatch")
    try:
        result_data = None

        try:
            result = await supabase.rpc(
                "process_delivery_payment",
                {
                    "p_tx_ref": tx_ref,
                    "p_flw_ref": flw_ref,

                    # FROM INTENT (not Redis)
                    "p_sender_id": intent["customer_id"],
                    "p_paid_amount": str(paid_amount),

                    # delivery
                    "p_pickup_location": delivery.get("pickup"),
                    "p_destination": delivery.get("dropoff"),
                    "p_receiver_phone": delivery.get("receiver_phone"),
                    "p_additional_info": delivery.get("notes"),

                    # package
                    "p_package_name": package.get("name"),
                    "p_duration": package.get("duration"),

                    # pricing (frozen values)
                    "p_distance": str(pricing.get("distance_km")),
                    "p_delivery_fee": str(pricing.get("delivery_fee")),

                    # meta
                    "p_payment_method": payment_method,
                },
            ).execute()

            result_data = result.data

        except APIError as e:
            result_data = extract_rpc_data(e)
            if not result_data:
                raise

        if not result_data:
            raise Exception("No data returned from RPC")

        # Already processed (DB-level idempotency)
        if result_data.get("status") == "already_processed":
            logger.info("delivery_payment_already_processed", tx_ref=tx_ref)
            return result_data

        order_id = result_data.get("order_id")
        delivery_fee = Decimal(str(result_data.get("delivery_fee", 0)))

        # 6. MARK INTENT COMPLETED
        await supabase.table("transaction_intents") \
            .update({
                "status": "COMPLETED",
                "flw_ref": flw_ref
            }) \
            .eq("tx_ref", tx_ref) \
            .execute()

        # 7. Notify user
        try:
            await notify_user(
                intent["customer_id"],
                "Payment Successful",
                f"Your delivery payment of ₦{delivery_fee} was successful.",
                data={
                    "type": "DELIVERY_PAYMENT_SUCCESS",
                    "order_id": order_id,
                    "amount": str(delivery_fee),
                },
                supabase=supabase,
            )
        except Exception as e:
            logger.error("notification_failed", error=str(e))

        logger.info(
            "delivery_payment_processed_success",
            tx_ref=tx_ref,
            order_id=order_id,
            payment_method=payment_method,
        )

        return result_data

    except Exception as e:
        logger.error(
            "delivery_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        raise

async def process_successful_delivery_payment_non_rpc(
    tx_ref: str,
    paid_amount: Decimal,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "WALLET", "BANK_TRANSFER", "PAY_ON_DELIVERY"],
    pending_data: dict = None,
):
    """
    Process successful delivery payments.
    Uses direct DB operations (like legacy code) for reliability.
    """
    logger.info("processing_delivery_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # 1. Verify payments
    # if payment_method == "CARD":
    #     verified = await verify_transaction_tx_ref(tx_ref)
    #     if not verified or verified.get("status") != "success":
    #         logger.error("delivery_payment_verification_failed", tx_ref=tx_ref)
    #         return {"status": "verification_failed"}

    # # 2. Get pending data from Redis
    # pending_key = f"pending_delivery_{tx_ref}"
    # pending = await get_pending(pending_key)

    if payment_method == "CARD":
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            logger.error("delivery_payment_verification_failed", tx_ref=tx_ref)
            return {"status": "verification_failed"}

    # 1. Get pending data from Redis
    pending_key = f"pending_delivery_{tx_ref}"
    if payment_method in {"WALLET", "PAY_ON_DELIVERY"} and pending_data:
        pending = pending_data
        logger.info("using_embedded_pending_data", tx_ref=tx_ref)
    else:
        pending = await get_pending(pending_key)  # CARD reads from Redis

    if not pending:
        logger.warning("delivery_payment_pending_not_found", tx_ref=tx_ref)
        return {"status": "pending_not_found"}

    sender_id = str(pending["sender_id"])
    delivery_data = pending["delivery_data"]
    distance = Decimal(str(pending.get("distance", 0)))

    # 3. Check if already processed (idempotency)
    existing = (
        await supabase.table("transfers")
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
        try:
            if payment_method == "CARD":
                await supabase.rpc(
                    "update_user_wallet",
                    {
                        "p_user_id": sender_id,
                        "p_balance_change": str(delivery_fee),
                        "p_escrow_balance_change": "0",
                    },
                ).execute()
        except APIError as e:
            wallet_result = extract_rpc_data(e)
            if not wallet_result:
                raise

        logger.info(
            "sender_wallet_credited", sender_id=sender_id, amount=str(delivery_fee)
        )

        # 9. Create DEPOSIT transaction
        await (
            supabase.table("transfers")
            .insert(
                {
                    "tx_ref": tx_ref,
                    "amount": str(delivery_fee),
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
                        "note": "Delivery payments received from Flutterwave",
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
                f"{sender_id}",
                "Payment Successful",
                f"Your delivery payments of ₦{delivery_fee} has been received.",
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
            "message": "Delivery payments processed successfully",
        }

    except Exception as e:
        logger.error(
            event="delivery_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        raise


# ───────────────────────────────────────────────
# Food Payment
# ───────────────────────────────────────────────
async def process_successful_food_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD",  "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
    request: Optional[Request] = None,
    # pending_data: dict = None,
):
    """Process successful food order payments using atomic RPC."""
    logger.info("processing_food_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # Verify payments
    if payment_method in ["CARD", "BANK_TRANSFER", 'BANK']:
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            logger.error("food_payment_verification_failed", tx_ref=tx_ref)
            return {"status": "verification_failed"}

    # 1. Get pending data from Redis
    
    intent_res = await supabase.table("transaction_intents") \
        .select("*") \
        .eq("tx_ref", tx_ref) \
        .single() \
        .execute()

    if not intent_res.data:
        raise Exception("Intent not found")

    intent = intent_res.data
    payload = intent["payload"]



    try:
        # Call atomic RPC
        result_data = None
        try:
            # result = await supabase.rpc(
            #     "process_food_payment",
            #     {
            #         "p_tx_ref": tx_ref,
            #         "p_flw_ref": flw_ref,
            #         "p_paid_amount": float(paid_amount),
            #         "p_customer_id": pending["customer_id"],
            #         "p_vendor_id": pending["vendor_id"],
            #         "p_order_data": pending["items"],
            #         "p_total_price": float(Decimal(pending["total_price"])),
            #         "p_delivery_fee": float(Decimal(pending.get("delivery_fee", 0))),
            #         "p_grand_total": float(Decimal(pending["grand_total"])),
            #         "p_delivery_option": pending["delivery_option"],
            #         "p_additional_info": pending.get("additional_info"),
            #         "p_customer_name": pending.get("name", "Customer"),
            #         "p_destination": pending.get("delivery_address", None),
            #         "p_payment_method": payment_method,
            #     },
            # ).execute()

            result = await supabase.rpc(
                "process_food_payment",
                {
                    "p_tx_ref": tx_ref,
                    "p_flw_ref": flw_ref,
                    "p_paid_amount": float(paid_amount),

                    # FROM INTENT
                    "p_customer_id": intent.get("customer_id"),
                    "p_vendor_id": intent.get("vendor_id"),
                    "p_order_data": payload.get("items"),

                    "p_total_price": float(intent.get("amount", 0)),
                    "p_delivery_fee": float(payload.get("pricing", {}).get("delivery_fee", 0)),
                    "p_grand_total": float(payload.get("pricing", {}).get("grand_total", 0)),

                    "p_delivery_option": payload.get("delivery", {}).get("option", ''),
                    "p_additional_info": payload.get("instructions"),
                    "p_customer_name": payload.get("customer", {}).get("phone", "Customer"),
                    "p_destination": payload.get("delivery", {}).get("address"),

                    "p_payment_method": payment_method,
                }
            ).execute()

            result_data = result.data

        except APIError as e:
            result_data = extract_rpc_data(e)
            if not result_data:
                raise

        if not result_data:
            raise Exception("No data returned from RPC")

        if result_data.get("status") == "already_processed":
            logger.info("food_payment_already_processed", tx_ref=tx_ref)
            return result_data


        order_id = result_data["order_id"]

        await supabase.table("transaction_intents") \
            .update({
                "status": "COMPLETED",
                "flw_ref": flw_ref
            }) \
            .eq("tx_ref", tx_ref) \
            .execute()

        # Notify vendor
        await notify_user(
            user_id=f"{result_data['vendor_id']}",
            title="New Order",
            body=f"You have a new order from {payload.get('customer', {}).get('phone', 'Customer')}",
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
            notes=f"Food order payments received via {payment_method}: {tx_ref}",
            request=request,
        )

        logger.info(
            "food_payment_processed_success", tx_ref=tx_ref, order_id=str(order_id)
        )

        return result_data

    except APIError as e:
        result_data = extract_rpc_data(e)
        if not result_data:
            logger.error(
                "food_payment_processing_error",
                tx_ref=tx_ref,
                error=str(result_data),
                exc_info=True,
            )
            raise

    # except Exception as e:
    #     logger.error(
    #         "food_payment_processing_error", tx_ref=tx_ref, error=str(e), exc_info=True
    #     )
    #     raise


# ───────────────────────────────────────────────
# Top-up Payment
# ───────────────────────────────────────────────
async def process_successful_topup_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "BANK_TRANSFER"] = "CARD",
    pending_data: dict = None,
    request: Optional[Request] = None,
):
    logger.info("processing_topup_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    # 1. Verify — CARD only
    if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            logger.error("topup_payment_verification_failed", tx_ref=tx_ref)
            return

    # 2. Idempotency check BEFORE anything else
    existing = (
        await supabase.table("transfers").select("id").eq("tx_ref", tx_ref).execute()
    )
    if existing.data:
        logger.info("topup_payment_already_processed", tx_ref=tx_ref)
        return {"status": "already_processed"}

    # 3. Get pending data
    pending_key = f"pending_topup_{tx_ref}"

    pending = await get_pending(pending_key)

    if not pending:
        logger.warning("topup_payment_pending_not_found", tx_ref=tx_ref)
        return

    expected_amount = Decimal(str(pending["amount"]))
    user_id = pending["user_id"]

    expected_rounded = expected_amount.quantize(Decimal("0.00"))
    paid_rounded = Decimal(str(paid_amount)).quantize(Decimal("0.00"))

    if paid_rounded != expected_rounded:
        logger.warning(
            "topup_payment_amount_mismatch",
            tx_ref=tx_ref,
            expected=str(expected_rounded),
            paid=str(paid_rounded),
        )
        await delete_pending(pending_key)
        return

    try:
        # 4. Call RPC
        result_data = None
        try:
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

        except APIError as e:
            result_data = extract_rpc_data(e)
            if not result_data:
                raise

        if not result_data:
            raise Exception("No data returned from RPC")

        if result_data.get("status") == "already_processed":
            logger.info("topup_payment_already_processed", tx_ref=tx_ref)
            await delete_pending(pending_key)
            return result_data

        await delete_pending(pending_key)

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

async def process_successful_product_payment(
    tx_ref: str,
    paid_amount: str,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
):
    logger.info("processing_product_payment", tx_ref=tx_ref)

    #  1. Verify
    if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            return {"status": "verification_failed"}

    #  2. FETCH INTENT
    intent_res = await supabase.table("transaction_intents") \
        .select("*") \
        .eq("tx_ref", tx_ref) \
        .single() \
        .execute()

    if not intent_res.data:
        return {"status": "intent_not_found"}

    intent = intent_res.data

    #  Idempotency
    if intent["status"] == "COMPLETED":
        return {"status": "already_processed"}

    payload = intent["payload"]

    product = payload["product"]
    order = payload["order"]
    pricing = payload["pricing"]
    delivery = payload["delivery"]

    paid = Decimal(str(paid_amount)).quantize(Decimal("0.00"))
    expected = Decimal(str(pricing["total"])).quantize(Decimal("0.00"))

    # 3. AMOUNT CHECK
    if paid != expected:
        logger.error("amount_mismatch", tx_ref=tx_ref)
        return {"status": "amount_mismatch"}

    try:
        result = await supabase.rpc(
            "process_product_payment",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,

                "p_customer_id": intent["customer_id"],
                "p_vendor_id": product["vendor_id"],
                "p_product_id": product["id"],

                "p_quantity": order["quantity"],
                "p_product_name": product["name"],

                "p_unit_price": pricing["unit_price"],
                "p_subtotal": pricing["subtotal"],
                "p_shipping_cost": pricing["shipping_cost"],
                "p_grand_total": pricing["total"],
                "p_paid_amount": str(paid),

                "p_delivery_option": delivery["option"],
                "p_delivery_address": delivery["address"],
                "p_additional_info": delivery.get("note"),

                "p_images": order.get("images"),
                "p_selected_size": order.get("selected_size"),
                "p_selected_color": order.get("selected_color"),

                "p_payment_method": payment_method,
            },
        ).execute()

        response = result.data

        if not response:
            raise Exception("No RPC response")

        if response.get("status") == "already_processed":
            return response

        #  4. MARK COMPLETED
        await supabase.table("transaction_intents") \
            .update({
                "status": "COMPLETED",
                "flw_ref": flw_ref
            }) \
            .eq("tx_ref", tx_ref) \
            .execute()

        #  Notify vendor
        await notify_user(
            user_id=product["vendor_id"],
            title="New Order",
            body="You have a new product order",
            data={"order_id": str(response.get("order_id"))},
            supabase=supabase,
        )

        logger.info("product_payment_success", tx_ref=tx_ref)

        return response

    except Exception as e:
        logger.error("product_payment_error", error=str(e))
        raise

# async def process_successful_product_payment(
#     tx_ref: str,
#     paid_amount: str,
#     flw_ref: str,
#     supabase: AsyncClient,
#     payment_method: Literal["CARD", "WALLET", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
#     pending_data: dict = None,
# ):
#     logger.info(
#         event="processing_product_payment",
#         tx_ref=tx_ref,
#         paid_amount=paid_amount,
#     )

#     if payment_method in ["CARD", "BANK_TRANSFER","BANK"]:
#         verified = await verify_transaction_tx_ref(tx_ref)
#         if not verified or verified.get("status") != "success":
#             logger.error("product_payment_verification_failed", tx_ref=tx_ref)
#             return {"status": "verification_failed"}

#     # 1. Get pending data from Redis
#     pending_key = f"pending_product_{tx_ref}"
#     if payment_method in {"WALLET", "PAY_ON_DELIVERY"} and pending_data:
#         pending = pending_data

#     else:
#         pending = await get_pending(pending_key)  # CARD reads from Redis

#     if not pending:
#         logger.warning(event="pending_order_not_found", tx_ref=tx_ref)
#         return

#     try:
#         delivery_option = pending.get("delivery_option", "PICKUP")
#         apply_shipping = delivery_option == "VENDOR_DELIVERY"
#         shipping = to_decimal(pending.get("shipping_cost"))
#         grand_total = to_decimal(pending.get("grand_total"))
#         paid_rounded = to_decimal(str(paid_amount)).quantize(Decimal("0.00"))
#         expected_rounded = grand_total.quantize(Decimal("0.00"))

#         # 2. Amount validation
#         if paid_rounded != expected_rounded:
#             logger.error(
#                 event="product_payment_amount_mismatch",
#                 tx_ref=tx_ref,
#                 expected=str(expected_rounded),
#                 paid=str(paid_rounded),
#             )
#             await delete_pending(pending_key)
#             return

#         # 3. Call RPC
#         response = None
#         try:
#             result = await supabase.rpc(
#                 "process_product_payment",
#                 {
#                     "p_tx_ref": tx_ref,
#                     "p_flw_ref": flw_ref,
#                     "p_customer_id": pending["customer_id"],
#                     "p_vendor_id": pending["vendor_id"],
#                     "p_product_id": pending["item_id"],
#                     "p_quantity": int(pending["quantity"]),
#                     "p_product_name": pending.get("product_name", "Product"),
#                     "p_unit_price": str(pending.get("price", 0))
#                     if pending.get("price") is not None
#                     else None,
#                     "p_subtotal": str(pending["subtotal"]),
#                     "p_shipping_cost": str(shipping) if apply_shipping else "0",
#                     "p_grand_total": str(grand_total),
#                     "p_paid_amount": str(paid_rounded),
#                     "p_delivery_option": pending["delivery_option"],
#                     "p_delivery_address": pending["delivery_address"],
#                     "p_additional_info": pending.get("additional_info"),
#                     "p_images": empty_to_none(pending.get("images")),
#                     "p_selected_size": empty_to_none(pending.get("selected_size")),
#                     "p_selected_color": empty_to_none(pending.get("selected_color")),
#                     "p_payment_method": payment_method,
#                 },
#             ).execute()

#             response = result.data

#         except APIError as e:
#             response = extract_rpc_data(e)
#             if not response:
#                 raise

#         if not response:
#             raise Exception("No data returned from RPC")

#         if response.get("status") == "already_processed":
#             logger.info(
#                 event="product_payment_already_processed",
#                 tx_ref=tx_ref,
#                 order_id=response.get("order_id"),
#             )
#             await delete_pending(pending_key)
#             return

#         logger.info(
#             event="product_payment_success",
#             tx_ref=tx_ref,
#             order_id=response.get("order_id"),
#             grand_total=str(grand_total),
#         )

#         # 4. Notify vendor
#         await notify_user(
#             user_id=pending["vendor_id"],
#             title="New Order",
#             body="You have a new product order",
#             data={
#                 "order_id": str(response.get("order_id")),
#                 "type": "PRODUCT_PAYMENT",
#             },
#             supabase=supabase,
#         )

#         await delete_pending(pending_key)

#     except Exception as e:
#         logger.error(
#             event="product_payment_processing_error",
#             tx_ref=tx_ref,
#             error=str(e),
#             exc_info=True,
#         )
#         raise


async def process_successful_product_payment_non_rpc(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "WALLET", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
    pending_data: dict = None,
):
    logger.info(
        event="processing_product_payment", tx_ref=tx_ref, paid_amount=paid_amount
    )

    if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            logger.error("product_payment_verification_failed", tx_ref=tx_ref)
            return {"status": "verification_failed"}

    # 1. Get pending data from Redis
    pending_key = f"pending_product_{tx_ref}"
    if payment_method in {"WALLET", "PAY_ON_DELIVERY"} and pending_data:
        pending = pending_data
        logger.info("using_embedded_pending_data", tx_ref=tx_ref)
    else:
        pending = await get_pending(pending_key)  # CARD reads from Redis

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
        await supabase.table("transfers").select("id").eq("tx_ref", tx_ref).execute()
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
            supabase.table("transfers")
            .insert(
                {
                    "tx_ref": tx_ref,
                    "amount": expected_total,
                    "from_user_id": customer_id,
                    "to_user_id": vendor_id,
                    "wallet_id": customer_id,
                    "order_id": order_id,
                    "transaction_type": "ESCROW_HOLD",
                    "payment_method": f"{payment_method}",
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

        raise


async def process_successful_laundry_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
    request: Optional[Request] = None,
):
    logger.info("processing_laundry_payment", tx_ref=tx_ref)

    #  1. Verify
    if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            return {"status": "verification_failed"}

    # 2. FETCH INTENT
    intent_res = await supabase.table("transaction_intents") \
        .select("*") \
        .eq("tx_ref", tx_ref) \
        .single() \
        .execute()

    if not intent_res.data:
        return {"status": "intent_not_found"}

    intent = intent_res.data

    # Idempotency
    if intent["status"] == "COMPLETED":
        return {"status": "already_processed"}

    payload = intent["payload"]

    vendor = payload["vendor"]
    pricing = payload["pricing"]
    schedule = payload["schedule"]
    meta = payload["meta"]
    items = payload["items"]

    # Safety check
    if float(intent["amount"]) != float(pricing["total"]):
        raise Exception("Amount mismatch")

    try:
        result = await supabase.rpc(
            "process_laundry_payment_new",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_paid_amount": str(paid_amount),

                "p_customer_id": intent["customer_id"],
                "p_vendor_id": vendor["id"],
                "p_order_data": items,

                "p_is_express": meta.get("is_express", False),
                "p_subtotal": pricing["subtotal"],
                "p_delivery_fee": pricing["delivery_fee"],
                "p_express_fee": pricing["express_fee"],
                "p_grand_total": pricing["total"],

                "p_delivery_option": meta.get("delivery_option"),
                "p_additional_info": meta.get("instructions"),

                "p_pickup_date": schedule.get("pickup_date"),
                "p_delivery_date": schedule.get("delivery_date"),
                "p_pickup_time": schedule.get("pickup_time"),
                "p_delivery_time": schedule.get("delivery_time"),

                "p_destination": meta.get("delivery_address"),

                "p_payment_method": payment_method,
            },
        ).execute()

        result_data = result.data

        if not result_data:
            raise Exception("No RPC response")

        if result_data.get("status") == "already_processed":
            return result_data

        # MARK COMPLETED
        await supabase.table("transaction_intents") \
            .update({
                "status": "COMPLETED",
                "flw_ref": flw_ref
            }) \
            .eq("tx_ref", tx_ref) \
            .execute()

        order_id = result_data["order_id"]

        # Notify vendor
        await notify_user(
            user_id=result_data["vendor_id"],
            title="New Laundry Order",
            body="You have a new laundry order",
            data={"order_id": str(order_id)},
            supabase=supabase,
        )

        logger.info("laundry_payment_success", tx_ref=tx_ref)

        return result_data

    except Exception as e:
        logger.error("laundry_payment_error", error=str(e))
        raise

# async def process_successful_laundry_payment(
#     tx_ref: str,
#     paid_amount: float,
#     flw_ref: str,
#     supabase: AsyncClient,
#     payment_method: Literal["CARD",  "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
#     pending_data: dict = None,
#     request: Optional[Request] = None,
# ):
#     """Process successful laundry order payments using atomic RPC."""
#     logger.info("processing_laundry_payment", tx_ref=tx_ref, paid_amount=paid_amount)

#     # Verify payments
#     # verified = await verify_transaction_tx_ref(tx_ref)
#     # if not verified or verified.get("status") != "success":
#     #     logger.error("laundry_payment_verification_failed", tx_ref=tx_ref)
#     #     return

#     # # Get pending data
#     # pending_key = f"pending_laundry_{tx_ref}"
#     # pending = await get_pending(pending_key)
#     if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
#         verified = await verify_transaction_tx_ref(tx_ref)
#         if not verified or verified.get("status") != "success":
#             logger.error("laundry_payment_verification_failed", tx_ref=tx_ref)
#             return {"status": "verification_failed"}

#     # 1. Get pending data from Redis
#     pending_key = f"pending_laundry_{tx_ref}"
#     if payment_method in {"WALLET", "PAY_ON_DELIVERY"} and pending_data:
#         pending = pending_data
#         logger.info("using_embedded_pending_data", tx_ref=tx_ref)
#     else:
#         pending = await get_pending(pending_key)  # CARD reads from Redis

#     if not pending:
#         logger.warning("laundry_payment_pending_not_found", tx_ref=tx_ref)
#         return

#     try:
#         # Call atomic RPC
#         result_data = None
#         try:
#             result = await supabase.rpc(
#                 "process_laundry_payment_new",
#                 {
#                     "p_tx_ref": tx_ref,
#                     "p_flw_ref": flw_ref,
#                     "p_paid_amount": str(paid_amount),
#                     "p_customer_id": pending["customer_id"],
#                     "p_vendor_id": pending["vendor_id"],
#                     "p_order_data": pending["items"],
#                     "p_is_express": pending.get("is_express", False),
#                     "p_subtotal": str(Decimal(pending["subtotal"])),
#                     "p_delivery_fee": str(Decimal(pending.get("delivery_fee", 0))),
#                     "p_delivery_time": pending.get("delivery_time") or None,
#                     "p_pickup_time": pending.get("pickup_time") or None,
#                     "p_grand_total": str(Decimal(pending["grand_total"])),
#                     "p_delivery_option": pending.get("delivery_option", "PICKUP"),
#                     "p_additional_info": pending.get("additional_info"),
#                     "p_customer_name": pending.get("name", "Customer"),
#                     "p_pickup_date": pending.get("pickup_date") or None,
#                     "p_delivery_date": pending.get("delivery_date") or None,
#                     "p_destination": pending.get("delivery_address", None),
#                     "p_express_fee": pending.get("express_fee", 0),
#                     "p_payment_method": payment_method,
#                 },
#             ).execute()

#             result_data = result.data

#         except APIError as e:
#             result_data = extract_rpc_data(e)
#             if not result_data:
#                 raise

#         if not result_data:
#             raise Exception("No data returned from RPC")

#         if result_data.get("status") == "already_processed":
#             logger.info("laundry_payment_already_processed", tx_ref=tx_ref)
#             await delete_pending(pending_key)
#             return result_data

#         # Success! Cleanup Redis
#         await delete_pending(pending_key)

#         order_id = result_data["order_id"]

#         # Notify vendor
#         await notify_user(
#             user_id=result_data["vendor_id"],
#             title="New Laundry Order",
#             body="You have a new laundry order",
#             data={"order_id": str(order_id), "type": "LAUNDRY_PAYMENT"},
#             supabase=supabase,
#         )

#         # Audit log
#         await log_audit_event(
#             supabase,
#             entity_type="LAUNDRY_ORDER",
#             entity_id=str(order_id),
#             action="PAYMENT_RECEIVED",
#             new_value={"payment_status": "PAID", "amount": result_data["grand_total"]},
#             actor_id=result_data["customer_id"],
#             actor_type="USER",
#             change_amount=Decimal(str(result_data["grand_total"])),
#             notes=f"Laundry payments received via {payment_method}: {tx_ref}",
#             request=request,
#         )

#         logger.info(
#             "laundry_payment_processed_success", tx_ref=tx_ref, order_id=str(order_id)
#         )

#         return result_data

#     except Exception as e:
#         logger.error(
#             "laundry_payment_processing_error",
#             tx_ref=tx_ref,
#             error=str(e),
#             exc_info=True,
#         )
#         raise


async def process_successful_reservation_payment(
    tx_ref: str,
    paid_amount: float,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "WALLET", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
    flw_ref: str,
    request: Optional[Request] = None,
):
    logger.info("payment_success", tx_ref=tx_ref)

    # 1. verify payment
    if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            return {"status": "verification_failed"}

    try:
        # 2. FINALIZE via DB (SOURCE OF TRUTH)
        result = await supabase.rpc(
            "finalize_reservation_from_intent",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_deposit_paid": paid_amount,
            },
        ).execute()

        result_data = result.data

        if not result_data:
            raise Exception("No data returned from finalize RPC")

        # 3. notify vendor
        await notify_user(
            user_id=result_data["vendor_id"],
            title="New Reservation",
            body="You have a confirmed reservation",
            data={
                "reservation_id": str(result_data["reservation_id"]),
                "type": "RESERVATION_PAYMENT",
            },
            supabase=supabase,
        )

        # 4. audit log
        await log_audit_event(
            supabase,
            entity_type="RESERVATION",
            entity_id=str(result_data["reservation_id"]),
            action="PAYMENT_RECEIVED",
            new_value={"amount": paid_amount},
            actor_id=result_data["customer_id"],
            actor_type="USER",
            change_amount=paid_amount,
            notes=f"Payment via {payment_method}: {tx_ref}",
            request=request,
        )

        logger.info("reservation_finalized_success", tx_ref=tx_ref)

        return result_data

    except Exception as e:
        logger.error("payment_processing_error", error=str(e))
        raise


def to_decimal(val, default="0"):
    if val is None or str(val).strip().lower() == "none":
        return Decimal(default)
    return Decimal(str(val))


def empty_to_none(val):
    """Convert empty lists to None so Postgres gets NULL instead of []"""
    if isinstance(val, list) and len(val) == 0:
        return None
    return val


def parse_coordinates(value) -> list:
    """Ensure coordinates are always a list for JSONB."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, tuple):
        return list(value)
    return value


async def process_pay_on_delivery(
    *,
    tx_ref: str,
    actor_id: str,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> dict:
    """
    Pay-on-delivery confirmation:
    - loads pending payload from Redis
    - validates ownership
    - processes the order using existing payment handlers with payment_method=PAY_ON_DELIVERY
    """
    if not tx_ref or "-" not in tx_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tx_ref"
        )

    if tx_ref.startswith("DELIVERY-"):
        pending_key = f"pending_delivery_{tx_ref}"
        handler = process_successful_delivery_payment
        owner_field = "sender_id"
        amount_field = "amount"
    elif tx_ref.startswith("FOOD-"):
        pending_key = f"pending_food_{tx_ref}"
        handler = process_successful_food_payment
        owner_field = "customer_id"
        amount_field = "grand_total"
    elif tx_ref.startswith("LAUNDRY-"):
        pending_key = f"pending_laundry_{tx_ref}"
        handler = process_successful_laundry_payment
        owner_field = "customer_id"
        amount_field = "grand_total"
    elif tx_ref.startswith("PRODUCT-"):
        pending_key = f"pending_product_{tx_ref}"
        handler = process_successful_product_payment
        owner_field = "customer_id"
        amount_field = "grand_total"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported tx_ref prefix"
        )

    pending = await get_pending(pending_key)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending record not found or expired",
        )

    if str(pending.get(owner_field)) != str(actor_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to confirm this payment",
        )

    raw_amount = pending.get(amount_field)
    if raw_amount is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pending record missing amount",
        )

    paid_amount = Decimal(str(raw_amount))

    # Use a synthetic ref; handlers store it alongside tx_ref.
    flw_ref = "PAY_ON_DELIVERY"

    # Reuse handlers, passing pending_data so they don't re-fetch Redis.
    # Handlers will delete the pending key on success / already_processed.
    if handler is process_successful_food_payment:
        return await handler(
            tx_ref=tx_ref,
            paid_amount=float(paid_amount),
            flw_ref=flw_ref,
            supabase=supabase,
            payment_method="PAY_ON_DELIVERY",
            request=request,
            pending_data=pending,
        )
    if handler is process_successful_laundry_payment:
        return await handler(
            tx_ref=tx_ref,
            paid_amount=float(paid_amount),
            flw_ref=flw_ref,
            supabase=supabase,
            payment_method="PAY_ON_DELIVERY",
            pending_data=pending,
            request=request,
        )
    if handler is process_successful_product_payment:
        return await handler(
            tx_ref=tx_ref,
            paid_amount=str(paid_amount),
            flw_ref=flw_ref,
            supabase=supabase,
            payment_method="PAY_ON_DELIVERY",
            pending_data=pending,
        )

    # Delivery handler expects Decimal
    return await handler(
        tx_ref=tx_ref,
        paid_amount=paid_amount,
        flw_ref=flw_ref,
        supabase=supabase,
        payment_method="PAY_ON_DELIVERY",
        pending_data=pending,
    )


#  Payout
class PaymentService:
    """Payout/Refund ptocessing"""

    def __init__(self, supabase: Client):
        self.supabase = supabase

    def mark_payout_success(
        self,
        order_id: str,
        flutterwave_tx_id: str,
        scheduled_payout_at: str,
    ):
        return self.supabase.rpc(
            "mark_payout_success",
            {
                "p_order_id": order_id,
                "p_flutterwave_tx_id": flutterwave_tx_id,
                "p_scheduled_payout_at": scheduled_payout_at,
            },
        ).execute()

    def get_due_payouts(self, limit: int = 20):
        return self.supabase.rpc(
            "get_due_payouts_locked",
            {"p_limit": limit},
        ).execute()

    def process_payout(
        self,
        order_payment_id: str,
        flutterwave_transfer_id: str,
        flutterwave_reference: str,
    ):
        return self.supabase.rpc(
            "process_payout",
            {
                "p_order_payment_id": order_payment_id,
                "p_flutterwave_transfer_id": flutterwave_transfer_id,
                "p_flutterwave_reference": flutterwave_reference,
            },
        ).execute()

    def create_refund(self, order_payment_id: str, amount: float, reason: str):
        return self.supabase.rpc(
            "create_refund",
            {
                "p_order_payment_id": order_payment_id,
                "p_amount": amount,
                "p_reason": reason,
            },
        ).execute()

    def get_pending_refunds(self, limit: int = 20):
        return self.supabase.rpc(
            "get_pending_refunds",
            {"p_limit": limit},
        ).execute()

    async def mark_refund_success(self, refund_id: str, flutterwave_refund_id: str):
        return self.supabase.rpc(
            "mark_refund_success",
            {
                "p_refund_id": refund_id,
                "p_flutterwave_refund_id": flutterwave_refund_id,
            },
        ).execute()
