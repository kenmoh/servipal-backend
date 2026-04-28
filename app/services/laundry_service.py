from uuid import UUID
import uuid
from datetime import datetime
from typing import Optional, List, Dict
from decimal import Decimal
from fastapi import HTTPException, status, Request
from app.utils.redis_utils import save_pending, get_pending
from app.schemas.common import (
    VendorOrderAction,
    PaymentInitializationResponse,
    PaymentCustomerInfo,
    PaymentCustomization,
)
from app.schemas.laundry_schemas import (
    LaundryVendorDetailResponse,
    LaundryCategoryResponse,
    LaundryItemResponse,
    LaundryItemDetailResponse,
    LaundryItemUpdate,
    LaundryVendorMarkReadyResponse,
    LaundryOrderCreate,
    LaundryCustomerConfirmResponse,
)
from app.utils.storage import upload_to_supabase_storage
from supabase import AsyncClient
from app.config.config import settings
from app.schemas.common import VendorResponse
from app.config.logging import logger
from app.utils.audit import log_audit_event
from app.services.payments.flutterwave_service import FlutterwavePaymentsClient
from app.services.vendors.payout_service import TransferService


# ───────────────────────────────────────────────
# Vendors & Detail
# ───────────────────────────────────────────────
async def get_laundry_vendors(
    supabase: AsyncClient, lat: Optional[float] = None, lng: Optional[float] = None
) -> List[VendorResponse]:
    params = {"near_lat": lat, "near_lng": lng} if lat and lng else {}
    resp = await supabase.rpc("get_laundry_vendors", params).execute()
    return [VendorResponse(**v) for v in resp.data]


async def get_laundry_vendor_detail(
    vendor_id: UUID, supabase: AsyncClient
) -> LaundryVendorDetailResponse:
    resp = await supabase.rpc(
        "get_laundry_vendor_detail_with_menu", {"vendor_user_id": str(vendor_id)}
    ).execute()

    if not resp.data:
        raise HTTPException(404, "Vendor not found")

    vendor_data = resp.data[0]["vendor_json"]
    menu_map = {}

    for row in resp.data:
        if row["category_json"]:
            cat = row["category_json"]
            if cat["id"] not in menu_map:
                menu_map[cat["id"]] = {
                    "category": LaundryCategoryResponse(**cat),
                    "items": [],
                }
            if row["item_json"]:
                menu_map[cat["id"]]["items"].append(
                    LaundryItemResponse(**row["item_json"])
                )

    return LaundryVendorDetailResponse(
        **vendor_data,
        categories=[m["category"] for m in menu_map.values()],
        menu=[item for m in menu_map.values() for item in m["items"]],
    )


async def _get_vendor_order_for_action(
    supabase: AsyncClient, 
    order_id: UUID, 
    vendor_id: UUID, 
    required_status: str = "PENDING",
    check_payment: bool = True
) -> dict:
    order_resp = (
        await supabase.table("laundry_orders")
        .select("id, vendor_id, order_status, payment_status, grand_total")
        .eq("id", str(order_id))
        .single()
        .execute()
    )

    if not order_resp.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Laundry order not found")

    order = order_resp.data

    if order["vendor_id"] != str(vendor_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your order")

    if order["order_status"] != required_status:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Order must be in {required_status} status (current status: {order['order_status']})",
        )

    if check_payment and order["payment_status"] != "PAID":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment not completed")

    return order


async def _process_order_refund(supabase: AsyncClient, order_id: UUID):
    # Get transaction for refund
    tx_resp = (
        await supabase.table("transactions")
        .select("id, amount, from_user_id, status")
        .eq("order_id", str(order_id))
        .single()
        .execute()
    )

    if not tx_resp.data:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Transaction not found for this order"
        )

    tx = tx_resp.data
    amount = tx["amount"]

    # Refund: escrow → customer balance (atomic RPC)
    await supabase.rpc(
        "update_wallet_balance",
        {
            "p_user_id": tx["from_user_id"],
            "p_delta": -amount,
            "p_field": "escrow_balance",
        },
    ).execute()

    await supabase.rpc(
        "update_wallet_balance",
        {
            "p_user_id": tx["from_user_id"],
            "p_delta": amount,
            "p_field": "balance",
        },
    ).execute()

    # Mark transaction as refunded
    await (
        supabase.table("transactions")
        .update({"status": "REFUNDED"})
        .eq("id", tx["id"])
        .execute()
    )


async def vendor_laundry_order_action(
    order_id: UUID, data: VendorOrderAction, vendor_id: UUID, supabase: AsyncClient
) -> LaundryVendorMarkReadyResponse:
    """
    Vendor accepts or rejects a laundry order.
    - On accept: move to PREPARING
    - On reject: cancel order + refund escrow to customer balance via RPC
    """
    try:
        # 1. Fetch & Validate (requires PENDING and PAID)
        await _get_vendor_order_for_action(supabase, order_id, vendor_id, required_status="PENDING", check_payment=True)

        # 2. Process action
        if data.action == "accept":
            new_status = "PREPARING"
            message = "Order accepted. Processing laundry now."
        else:  # reject
            new_status = "CANCELLED"
            message = "Order rejected."
            await _process_order_refund(supabase, order_id)

        # 3. Update order status
        await _update_order_status(supabase, order_id, new_status)

        return LaundryVendorMarkReadyResponse(
            order_id=order_id, order_status=new_status, message=message
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(
            "vendor_laundry_order_action_failed",
            order_id=str(order_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Order action failed: {str(e)}")


async def _get_laundry_order_or_404(supabase: AsyncClient, order_id: UUID, customer_id: UUID) -> dict:
    order_resp = (
        await supabase.table("laundry_orders")
        .select("id, customer_id, vendor_id, order_status, grand_total")
        .eq("id", str(order_id))
        .single()
        .execute()
    )

    if not order_resp.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Laundry order not found")

    order = order_resp.data

    # Security & validation
    if order["customer_id"] != str(customer_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This is not your order"
        )

    if order["order_status"] != "READY":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order not ready for confirmation yet. Current status: {order['order_status']}",
        )
    return order


async def _get_transaction(supabase: AsyncClient, order_id: UUID):
    tx_resp = (
        await supabase.table("transactions")
        .select("id, amount, to_user_id, status")
        .eq("order_id", str(order_id))
        .single()
        .execute()
    )

    if not tx_resp.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found for this order")

    tx = tx_resp.data

    if tx["status"] == "RELEASED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order already confirmed and payments released",
        )

    full_amount = tx["amount"]
    vendor_id = tx["to_user_id"]
    return vendor_id, full_amount, tx


async def _update_transaction_status(supabase, tx):
    await (
        supabase.table("transactions")
        .update({"status": "RELEASED"})
        .eq("id", tx["id"])
        .execute()
    )


async def _update_order_status(supabase: AsyncClient, order_id: UUID, new_status: str):
    await (
        supabase.table("laundry_orders")
        .update({"order_status": new_status})
        .eq("id", str(order_id))
        .execute()
    )


async def _trigger_payout(
    base_url: str, secret_key: str, order_id: UUID, payout_to: str, supabase: AsyncClient, vendor_id: UUID
):
    try:
        transfer_service = TransferService(
            base_url=base_url,
            secret_key=secret_key,
        )
        await transfer_service.create_transfer(
            order_id=str(order_id),
            payout_to=payout_to,
            supabase=supabase,
        )
        logger.info(
            "laundry_transfer_initiated",
            order_id=str(order_id),
            vendor_id=str(vendor_id),
        )
    except Exception as transfer_err:
        logger.error(
            "laundry_transfer_failed",
            order_id=str(order_id),
            error=str(transfer_err),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to trigger payout. Please try again later.",
        )


async def _payment_release(supabase, customer_id, vendor_id, order, full_amount):
    await supabase.rpc(
        "release_order_payment",
        {
            "p_customer_id": str(customer_id),
            "p_vendor_id": str(vendor_id) if vendor_id else str(order["vendor_id"]),
            "p_full_amount": full_amount,
        },
    ).execute()


async def customer_confirm_laundry_order(
    order_id: UUID,
    customer_id: UUID,
    supabase: AsyncClient,
    request: Optional[Request] = None,
) -> LaundryCustomerConfirmResponse:
    """
    Customer confirms receipt of laundry order.
    - Deducts full amount from customer escrow
    - Credits full amount to vendor balance (via atomic RPC)
    - Updates transaction to RELEASED
    - Updates order to COMPLETED
    """
    logger.info(
        "customer_confirm_laundry_order",
        order_id=str(order_id),
        customer_id=str(customer_id),
    )
    try:
        # 1. Fetch order with necessary fields
        order = await _get_laundry_order_or_404(supabase, order_id, customer_id)

        # 3. Get transaction (for amount & prevent double-release)
        vendor_id, full_amount, tx = await _get_transaction(supabase, order_id)

        # 4. Atomic payments release (deduct escrow → credit balance)
        await _payment_release(supabase, customer_id, vendor_id, order, full_amount)

        # 5. Update transaction status
        await _update_transaction_status(supabase, tx)

        # 6. Update order status
        await _update_order_status(supabase, order_id, "COMPLETED")

        # Audit log
        await log_audit_event(
            supabase,
            entity_type="LAUNDRY_ORDER",
            entity_id=str(order_id),
            action="CUSTOMER_CONFIRM",
            old_value={"order_status": "READY", "escrow_status": "HELD"},
            new_value={"order_status": "COMPLETED", "escrow_status": "RELEASED"},
            change_amount=Decimal(str(full_amount)),
            actor_id=str(customer_id),
            actor_type="USER",
            notes=f"Customer confirmed laundry order, payments released to vendor",
            request=request,
        )

        # Trigger payout to vendor via Flutterwave transfer
        await _trigger_payout(
            settings.FLUTTERWAVE_BASE_URL,
            settings.FLW_SECRET_KEY,
            order_id,
            "VENDOR",
            supabase,
            vendor_id,
        )

        logger.info(
            "customer_confirm_laundry_order_success",
            order_id=str(order_id),
            amount_released=float(full_amount),
        )
        return LaundryCustomerConfirmResponse(
            order_id=order_id,
            amount_released=full_amount,
            message="Order confirmed! Payment released to vendor.",
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(
            "customer_confirm_laundry_order_error",
            order_id=str(order_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Confirmation failed: {str(e)}",
        )


# ───────────────────────────────────────────────
# Menu Management
# ───────────────────────────────────────────────
async def create_laundry_item_with_images(
    name: str,
    vendor_id: UUID,
    price: Decimal,
    description: Optional[str],
    supabase: AsyncClient,
    images=None,
) -> dict:
    if images is None:
        images = []
    try:
        item_resp = (
            await supabase.table("laundry_items")
            .insert(
                {
                    "vendor_id": str(vendor_id),
                    "name": name,
                    "description": description,
                    "price": float(price),
                }
            )
            .execute()
        )

        item_id = item_resp.data[0]["id"]

        image_urls = []
        for file in images:
            url = await upload_to_supabase_storage(
                file=file,
                bucket="menu-images",
                folder=f"vendor_{vendor_id}/laundry_item_{item_id}",
                supabase=supabase,
            )
            image_urls.append(url)

        if image_urls:
            await (
                supabase.table("laundry_items")
                .update({"images": image_urls})
                .eq("id", item_id)
                .execute()
            )

        return {"success": True, "item_id": item_id, "image_urls": image_urls}

    except Exception as e:
        raise HTTPException(500, f"Failed to create laundry item: {str(e)}")


# ───────────────────────────────────────────────
# Payment Initiation Helpers
# ───────────────────────────────────────────────
async def _get_laundry_vendor_details(
    supabase: AsyncClient, data: LaundryOrderCreate
) -> dict:
    vendor_res = await supabase.rpc(
        "get_vendor_with_availability",
        {
            "p_vendor_id": str(data.vendor_id),
            "p_type": data.delivery_option,
            "p_date": data.pickup_date,
        },
    ).execute()

    if not vendor_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Laundry vendor not found")

    return vendor_res.data


async def _validate_and_calculate_items(
    supabase: AsyncClient, vendor_id: UUID, cart_items: List
) -> tuple[Decimal, List[dict]]:
    item_ids = [str(item.item_id) for item in cart_items]
    db_items = (
        await supabase.table("laundry_items")
        .select("id, name, price, vendor_id")
        .in_("id", item_ids)
        .eq("vendor_id", str(vendor_id))
        .execute()
    )

    items_map = {item["id"]: item for item in db_items.data}
    subtotal = Decimal("0")
    normalized_items = []

    for cart_item in cart_items:
        db_item = items_map.get(str(cart_item.item_id))
        if not db_item:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid laundry item")

        item_total = Decimal(str(db_item["price"])) * cart_item.quantity
        subtotal += item_total

        normalized_items.append(
            {
                "item_id": db_item["id"],
                "name": db_item["name"],
                "price": str(db_item["price"]),
                "quantity": cart_item.quantity,
                "total": str(item_total),
            }
        )

    return subtotal, normalized_items


def _calculate_laundry_fees(vendor: dict, delivery_option: str) -> Decimal:
    delivery_fee = Decimal("0")
    if delivery_option == "VENDOR_DELIVERY":
        if not vendor.get("can_pickup_and_dropoff"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Vendor does not offer delivery"
            )
        delivery_fee = Decimal(str(vendor.get("pickup_and_delivery_charge") or 0))
    return delivery_fee


async def _save_transaction_intent(
    supabase: AsyncClient,
    tx_ref: str,
    customer_id: UUID,
    amount: Decimal,
    payload: dict,
):
    await (
        supabase.table("transaction_intents")
        .insert(
            {
                "tx_ref": tx_ref,
                "customer_id": str(customer_id),
                "amount": str(amount),
                "currency": "NGN",
                "service_type": "LAUNDRY",
                "status": "PENDING",
                "payload": payload,
            }
        )
        .execute()
    )


# ───────────────────────────────────────────────
# Payment Initiation (Pay First)
# ───────────────────────────────────────────────
async def initiate_laundry_payment(
    data: LaundryOrderCreate,
    customer_id: UUID,
    customer_info: dict,
    supabase: AsyncClient,
    request: "Request | None" = None,
) -> dict:
    try:
        # 1. Vendor & Items Validation
        vendor = await _get_laundry_vendor_details(supabase, data)
        subtotal, normalized_items = await _validate_and_calculate_items(
            supabase, data.vendor_id, data.items
        )

        # 2. Fee Calculation
        delivery_fee = _calculate_laundry_fees(vendor, data.delivery_option)
        express_fee = Decimal(vendor.get("express_fee", "0"))
        grand_total = subtotal + delivery_fee + express_fee

        # 3. Build Intent Payload
        tx_ref = f"LAUNDRY-{uuid.uuid4().hex[:32].upper()}"
        payload = {
            "vendor": {"id": str(data.vendor_id), "name": vendor["business_name"]},
            "items": normalized_items,
            "pricing": {
                "subtotal": str(subtotal),
                "delivery_fee": str(delivery_fee),
                "express_fee": str(express_fee),
                "total": str(grand_total),
            },
            "schedule": {
                "pickup_date": data.pickup_date,
                "delivery_date": data.delivery_date,
                "pickup_time": data.pickup_time,
                "delivery_time": data.delivery_time,
            },
            "meta": {
                "delivery_option": data.delivery_option,
                "is_express": data.is_express,
                "instructions": data.instructions,
                "delivery_address": data.delivery_address,
            },
        }

        # Fraud / risk evaluation before persisting the intent (critical action).
        try:
            from app.schemas.fraud_schemas import FraudEvaluationEvent
            from app.services.fraud import FraudService

            fraud = FraudService(supabase)
            assessment = await fraud.evaluate(
                event=FraudEvaluationEvent.PAYMENT_INITIATION,
                user_id=str(customer_id),
                vendor_id=str(data.vendor_id),
                amount=grand_total,
                tx_ref=tx_ref,
                order_type="LAUNDRY",
                request=request,
                details={"delivery_option": data.delivery_option, "is_express": data.is_express},
            )
            await fraud.enforce(assessment=assessment)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("fraud_eval_failed", event="PAYMENT_INITIATION", error=str(e))

        # 4. Persist Intent
        await _save_transaction_intent(supabase, tx_ref, customer_id, grand_total, payload)

        # 5. Return Flutterwave config
        return PaymentInitializationResponse(
            tx_ref=tx_ref,
            amount=grand_total,
            public_key=settings.FLUTTERWAVE_PUBLIC_KEY,
            currency="NGN",
            customer=PaymentCustomerInfo(
                email=customer_info.get("email"),
                phone_number=customer_info.get("phone_number"),
                full_name=customer_info.get("full_name") or "N/A",
            ),
            customization=PaymentCustomization(
                title="Servipal Laundry",
                description=f"{vendor['business_name']} - Laundry Order",
                logo="https://mohdelivery.s3.us-east-1.amazonaws.com/favion/favicon.ico",
            ),
            message="Ready for payment",
        ).model_dump()

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(
            "laundry_initiation_failed",
            customer_id=str(customer_id),
            vendor_id=str(data.vendor_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Laundry initiation failed: {str(e)}")


async def update_laundry_item(
    item_id: UUID, data: LaundryItemUpdate, vendor_id: UUID, supabase: AsyncClient
) -> LaundryItemDetailResponse:
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No data provided")

    item = (
        await supabase.table("laundry_items")
        .select("vendor_id")
        .eq("id", str(item_id))
        .single()
        .execute()
    )
    if item.data["vendor_id"] != str(vendor_id):
        raise HTTPException(403, "Not your item")

    resp = (
        await supabase.table("laundry_items")
        .update(update_data)
        .eq("id", str(item_id))
        .execute()
    )
    return LaundryItemDetailResponse(**resp.data[0])


async def delete_laundry_item(item_id: UUID, vendor_id: UUID, supabase: AsyncClient):
    item = (
        await supabase.table("laundry_items")
        .select("vendor_id")
        .eq("id", str(item_id))
        .single()
        .execute()
    )
    if item.data["vendor_id"] != str(vendor_id):
        raise HTTPException(403, "Not your item")

    await (
        supabase.table("laundry_items")
        .update({"is_deleted": True})
        .eq("id", str(item_id))
        .execute()
    )
    return {"success": True, "message": "Item deleted"}


async def vendor_mark_laundry_order_ready(
    order_id: UUID, vendor_id: UUID, supabase: AsyncClient
) -> LaundryVendorMarkReadyResponse:
    try:
        # 1. Fetch & Validate (requires PREPARING)
        await _get_vendor_order_for_action(
            supabase, order_id, vendor_id, required_status="PREPARING", check_payment=False
        )

        # 2. Update status to READY
        await _update_order_status(supabase, order_id, "READY")

        return LaundryVendorMarkReadyResponse(order_id=order_id)
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(
            "vendor_mark_laundry_order_ready_failed",
            order_id=str(order_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to mark ready: {str(e)}")
