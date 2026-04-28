import json
from typing import Literal
from datetime import datetime, timezone
from app.utils.redis_utils import get_pending, delete_pending
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



# ───────────────────────────────────────────────
# Payment Processing Helpers
# ───────────────────────────────────────────────
async def _verify_payment_status(payment_method: str, tx_ref: str) -> bool:
    if payment_method in ["CARD", "BANK_TRANSFER", "BANK"]:
        verified = await verify_transaction_tx_ref(tx_ref)
        if not verified or verified.get("status") != "success":
            logger.error("payment_verification_failed", tx_ref=tx_ref)
            return False
    return True


async def _get_payment_intent(supabase: AsyncClient, tx_ref: str) -> dict:
    intent_res = (
        await supabase.table("transaction_intents")
        .select("*")
        .eq("tx_ref", tx_ref)
        .single()
        .execute()
    )

    if not intent_res.data:
        logger.error("intent_not_found", tx_ref=tx_ref)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment intent not found")

    intent = intent_res.data

    # Idempotency check
    if intent["status"] == "COMPLETED":
        logger.info("already_processed", tx_ref=tx_ref)
        return intent, True  # Already processed

    # Expiry check
    if intent.get("expires_at"):
        if datetime.fromisoformat(intent["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment intent expired")

    return intent, False


async def _finalize_payment_intent(supabase: AsyncClient, tx_ref: str, flw_ref: str):
    await (
        supabase.table("transaction_intents")
        .update({"status": "COMPLETED", "flw_ref": flw_ref})
        .eq("tx_ref", tx_ref)
        .execute()
    )


async def _run_delivery_payment_rpc(
    supabase: AsyncClient,
    intent: dict,
    flw_ref: str,
    paid_amount: Decimal,
    payment_method: str,
    tx_ref: str,
) -> dict:
    payload = intent["payload"]
    delivery = payload.get("delivery", {})
    package = payload.get("package", {})
    pricing = payload.get("pricing", {})

    if float(intent["amount"]) != float(pricing.get("total")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Amount mismatch")

    try:
        result = await supabase.rpc(
            "process_delivery_payment",
            {
                "p_additional_info": delivery.get("notes"),
                "p_delivery_type": delivery.get("delivery_type", "STANDARD"),
                "p_destination": delivery.get("dropoff"),
                "p_distance": str(pricing.get("distance_km")),
                "p_dropoff_coordinates": delivery.get("dropoff_coordinates"),
                "p_duration": package.get("duration"),
                "p_flw_ref": flw_ref,
                "p_package_image_url": package.get("image_url"),
                "p_package_name": package.get("name"),
                "p_paid_amount": str(paid_amount),
                "p_payment_method": payment_method,
                "p_pickup_coordinates": delivery.get("pickup_coordinates"),
                "p_pickup_location": delivery.get("pickup"),
                "p_receiver_phone": delivery.get("receiver_phone"),
                "p_sender_id": intent["customer_id"],
                "p_sender_phone_number": delivery.get("sender_phone_number"),
                "p_tx_ref": tx_ref,
            },
        ).execute()
        return result.data

    except APIError as e:
        result_data = extract_rpc_data(e)
        if result_data:
            return result_data
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"RPC Error: {str(e)}"
        )


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

    try:
        # 1. Verify payment
        if not await _verify_payment_status(payment_method, tx_ref):
            return {"status": "verification_failed"}

        # 2. Fetch & Validate Intent
        intent, already_processed = await _get_payment_intent(supabase, tx_ref)
        if already_processed:
            return {"status": "already_processed"}

        # 3. Execute atomic RPC
        result_data = await _run_delivery_payment_rpc(
            supabase, intent, flw_ref, paid_amount, payment_method, tx_ref
        )

        if not result_data:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No data returned from RPC")

        # Double check DB-level idempotency
        if result_data.get("status") == "already_processed":
            logger.info("delivery_payment_already_processed", tx_ref=tx_ref)
            return result_data

        # 4. Finalize Intent
        await _finalize_payment_intent(supabase, tx_ref, flw_ref)

        # 5. Notify user
        order_id = result_data.get("order_id")
        delivery_fee = result_data.get("delivery_fee", 0)
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

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(
            "delivery_payment_processing_error",
            tx_ref=tx_ref,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Delivery payment processing failed: {str(e)}"
        )


async def _run_food_payment_rpc(
    supabase: AsyncClient,
    intent: dict,
    flw_ref: str,
    paid_amount: float,
    payment_method: str,
    tx_ref: str,
) -> dict:
    payload = intent["payload"]
    try:
        result = await supabase.rpc(
            "process_food_payment",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_paid_amount": float(paid_amount),
                "p_customer_id": intent.get("customer_id"),
                "p_vendor_id": intent.get("vendor_id"),
                "p_order_data": payload.get("items"),
                "p_total_price": float(intent.get("amount", 0)),
                "p_delivery_fee": float(
                    payload.get("pricing", {}).get("delivery_fee", 0)
                ),
                "p_grand_total": float(
                    payload.get("pricing", {}).get("grand_total", 0)
                ),
                "p_delivery_option": payload.get("delivery", {}).get("option", ""),
                "p_additional_info": payload.get("instructions"),
                "p_customer_name": payload.get("customer", {}).get(
                    "phone", "Customer"
                ),
                "p_destination": payload.get("delivery", {}).get("address"),
                "p_payment_method": payment_method,
            },
        ).execute()
        return result.data
    except APIError as e:
        result_data = extract_rpc_data(e)
        if result_data:
            return result_data
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"RPC Error: {str(e)}"
        )


# ───────────────────────────────────────────────
# Food Payment
# ───────────────────────────────────────────────
async def process_successful_food_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
    request: Optional[Request] = None,
):
    """Process successful food order payments using atomic RPC."""
    logger.info("processing_food_payment", tx_ref=tx_ref, paid_amount=paid_amount)

    try:
        # 1. Verify payment
        if not await _verify_payment_status(payment_method, tx_ref):
            return {"status": "verification_failed"}

        # 2. Fetch & Validate Intent
        intent, already_processed = await _get_payment_intent(supabase, tx_ref)
        if already_processed:
            return {"status": "already_processed"}

        # 3. Execute atomic RPC
        result_data = await _run_food_payment_rpc(
            supabase, intent, flw_ref, paid_amount, payment_method, tx_ref
        )

        if not result_data:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No data returned from RPC")

        # Double check DB-level idempotency
        if result_data.get("status") == "already_processed":
            logger.info("food_payment_already_processed", tx_ref=tx_ref)
            return result_data

        # 4. Finalize Intent
        await _finalize_payment_intent(supabase, tx_ref, flw_ref)

        order_id = result_data["order_id"]

        await (
            supabase.table("transaction_intents")
            .update({"status": "COMPLETED", "flw_ref": flw_ref})
            .eq("tx_ref", tx_ref)
            .execute()
        )

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
        await supabase.table("transactions").select("id").eq("tx_ref", tx_ref).execute()
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


async def _run_product_payment_rpc(
    supabase: AsyncClient,
    intent: dict,
    flw_ref: str,
    paid_amount: str,
    payment_method: str,
    tx_ref: str,
) -> dict:
    payload = intent["payload"]
    product = payload["product"]
    order = payload["order"]
    pricing = payload["pricing"]
    delivery = payload["delivery"]

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
                "p_paid_amount": str(paid_amount),
                "p_delivery_option": delivery["option"],
                "p_delivery_address": delivery["address"],
                "p_additional_info": delivery.get("note"),
                "p_images": order.get("images"),
                "p_selected_size": order.get("selected_size"),
                "p_selected_color": order.get("selected_color"),
                "p_payment_method": payment_method,
            },
        ).execute()

        return result.data
    except APIError as e:
        result_data = extract_rpc_data(e)
        if result_data:
            return result_data
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"RPC Error: {str(e)}"
        )


async def _run_laundry_payment_rpc(
    supabase: AsyncClient,
    intent: dict,
    flw_ref: str,
    paid_amount: float,
    payment_method: str,
    tx_ref: str,
) -> dict:
    payload = intent["payload"]
    vendor = payload["vendor"]
    pricing = payload["pricing"]
    schedule = payload["schedule"]
    meta = payload["meta"]
    items = payload["items"]

    if float(intent["amount"]) != float(pricing["total"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Amount mismatch")

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

        return result.data
    except APIError as e:
        result_data = extract_rpc_data(e)
        if result_data:
            return result_data
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"RPC Error: {str(e)}"
        )


async def _run_reservation_payment_rpc(
    supabase: AsyncClient,
    tx_ref: str,
    flw_ref: str,
    paid_amount: float,
) -> dict:
    try:
        result = await supabase.rpc(
            "finalize_reservation_from_intent",
            {
                "p_tx_ref": tx_ref,
                "p_flw_ref": flw_ref,
                "p_deposit_paid": paid_amount,
            },
        ).execute()
        return result.data
    except APIError as e:
        result_data = extract_rpc_data(e)
        if result_data:
            return result_data
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"RPC Error: {str(e)}"
        )


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

    try:
        # 1. Verify payment
        if not await _verify_payment_status(payment_method, tx_ref):
            return {"status": "verification_failed"}

        # 2. Fetch & Validate Intent
        intent, already_processed = await _get_payment_intent(supabase, tx_ref)
        if already_processed:
            return {"status": "already_processed"}

        # 3. Execute atomic RPC
        result_data = await _run_product_payment_rpc(
            supabase, intent, flw_ref, paid_amount, payment_method, tx_ref
        )

        if not result_data:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No data returned from RPC")

        # Double check DB-level idempotency
        if result_data.get("status") == "already_processed":
            logger.info("product_payment_already_processed", tx_ref=tx_ref)
            return result_data

        # 4. Finalize Intent
        await _finalize_payment_intent(supabase, tx_ref, flw_ref)

        # 5. Notify vendor
        await notify_user(
            user_id=result_data.get("vendor_id"),
            title="New Order",
            body="You have a new product order",
            data={"order_id": str(result_data.get("order_id"))},
            supabase=supabase,
        )

        logger.info("product_payment_success", tx_ref=tx_ref)
        return result_data

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error("product_payment_error", error=str(e))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Product payment processing failed: {str(e)}"
        )




async def process_successful_laundry_payment(
    tx_ref: str,
    paid_amount: float,
    flw_ref: str,
    supabase: AsyncClient,
    payment_method: Literal["CARD", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"],
    request: Optional[Request] = None,
):
    logger.info("processing_laundry_payment", tx_ref=tx_ref)

    try:
        # 1. Verify payment
        if not await _verify_payment_status(payment_method, tx_ref):
            return {"status": "verification_failed"}

        # 2. Fetch & Validate Intent
        intent, already_processed = await _get_payment_intent(supabase, tx_ref)
        if already_processed:
            return {"status": "already_processed"}

        # 3. Execute atomic RPC
        result_data = await _run_laundry_payment_rpc(
            supabase, intent, flw_ref, paid_amount, payment_method, tx_ref
        )

        if not result_data:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No RPC response")

        # Double check DB-level idempotency
        if result_data.get("status") == "already_processed":
            return result_data

        # 4. Finalize Intent
        await _finalize_payment_intent(supabase, tx_ref, flw_ref)

        order_id = result_data["order_id"]

        # 5. Notify vendor
        await notify_user(
            user_id=result_data["vendor_id"],
            title="New Laundry Order",
            body="You have a new laundry order",
            data={"order_id": str(order_id)},
            supabase=supabase,
        )

        logger.info("laundry_payment_success", tx_ref=tx_ref)
        return result_data

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error("laundry_payment_error", error=str(e))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Laundry payment processing failed: {str(e)}"
        )


async def process_successful_reservation_payment(
    tx_ref: str,
    paid_amount: float,
    supabase: AsyncClient,
    payment_method: Literal[
        "CARD", "WALLET", "BANK_TRANSFER", "PAY_ON_DELIVERY", "BANK"
    ],
    flw_ref: str,
    request: Optional[Request] = None,
):
    logger.info("processing_reservation_payment", tx_ref=tx_ref)

    try:
        # 1. Verify payment
        if not await _verify_payment_status(payment_method, tx_ref):
            return {"status": "verification_failed"}

        # 2. Fetch & Validate Intent
        intent, already_processed = await _get_payment_intent(supabase, tx_ref)
        if already_processed:
            return {"status": "already_processed"}

        # 3. Execute atomic RPC
        result_data = await _run_reservation_payment_rpc(
            supabase, tx_ref, flw_ref, paid_amount
        )

        if not result_data:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No data returned from RPC")

        # Double check DB-level idempotency
        if result_data.get("status") == "already_processed":
            return result_data

        # 4. Finalize Intent
        await _finalize_payment_intent(supabase, tx_ref, flw_ref)

        # 5. Notify vendor
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

        # 6. Audit log
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

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error("reservation_payment_error", error=str(e))
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Reservation payment processing failed: {str(e)}"
        )


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
        )
    if handler is process_successful_laundry_payment:
        return await handler(
            tx_ref=tx_ref,
            paid_amount=float(paid_amount),
            flw_ref=flw_ref,
            supabase=supabase,
            payment_method="PAY_ON_DELIVERY",
            request=request,
        )
    if handler is process_successful_product_payment:
        return await handler(
            tx_ref=tx_ref,
            paid_amount=str(paid_amount),
            flw_ref=flw_ref,
            supabase=supabase,
            payment_method="PAY_ON_DELIVERY",
        )

    # Delivery handler expects Decimal
    return await handler(
        tx_ref=tx_ref,
        paid_amount=paid_amount,
        flw_ref=flw_ref,
        supabase=supabase,
        payment_method="PAY_ON_DELIVERY",
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
