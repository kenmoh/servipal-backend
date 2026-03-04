from uuid import UUID
import uuid
from datetime import datetime
from app.schemas.product_schemas import (
    ProductItemCreate,
    ProductItemUpdate,
    ProductItemResponse,
    ProductOrderCreate,
    UpdateOrderStatusRequest,
    ProductVendorMarkReadyResponse,
)
from fastapi import HTTPException, status
from supabase import AsyncClient
from decimal import Decimal
from typing import List
from app.utils.redis_utils import save_pending
from app.config.config import settings
from app.schemas.common import (
    PaymentInitializationResponse,
    PaymentCustomerInfo,
    PaymentCustomization,
)
from app.services.notification_service import notify_user
from app.config.logging import logger
from postgrest.exceptions import APIError


# from app.utils.commission import get_commission_rate


# ───────────────────────────────────────────────
# CREATE - Any authenticated user can create
# ───────────────────────────────────────────────
async def create_product_item(
    data: ProductItemCreate, vendor_id: UUID, supabase: AsyncClient
) -> ProductItemResponse:
    try:
        item_data = data.model_dump()
        item_data["vendor_id"] = str(vendor_id)
        item_data["total_sold"] = 0

        resp = await supabase.table("product_items").insert(item_data).execute()

        if not resp.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create product item",
            )

        return ProductItemResponse(**resp.data[0])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create product failed: {str(e)}",
        )


# ───────────────────────────────────────────────
# READ - Get single item (public)
# ───────────────────────────────────────────────
async def get_product_item(item_id: UUID, supabase: AsyncClient) -> ProductItemResponse:
    item = (
        await supabase.table("product_items")
        .select("*")
        .eq("id", str(item_id))
        .eq("is_deleted", False)
        .single()
        .execute()
    )

    if not item.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product item not found or deleted",
        )

    return ProductItemResponse(**item.data)


# ───────────────────────────────────────────────
# READ - Seller's own items
# ───────────────────────────────────────────────
async def get_my_product_items(
    vendor_id: UUID, supabase: AsyncClient
) -> List[ProductItemResponse]:
    items = (
        await supabase.table("product_items")
        .select("*")
        .eq("vendor_id", str(vendor_id))
        .eq("is_deleted", False)
        .order("created_at", desc=True)
        .execute()
    )

    return [ProductItemResponse(**item) for item in items.data]


# ───────────────────────────────────────────────
# UPDATE - Only owner can update
# ───────────────────────────────────────────────
async def update_product_item(
    item_id: UUID, data: ProductItemUpdate, vendor_id: UUID, supabase: AsyncClient
) -> ProductItemResponse:
    # Check ownership
    item = (
        await supabase.table("product_items")
        .select("vendor_id")
        .eq("id", str(item_id))
        .single()
        .execute()
    )

    if not item.data or item.data["vendor_id"] != str(vendor_id):
        raise HTTPException(403, "Not your product item")

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No fields to update")

    resp = (
        await supabase.table("product_items")
        .update(update_data)
        .eq("id", str(item_id))
        .execute()
    )

    return ProductItemResponse(**resp.data[0])


# ───────────────────────────────────────────────
# DELETE - Soft delete (only owner)
# ───────────────────────────────────────────────
async def delete_product_item(
    item_id: UUID, vendor_id: UUID, supabase: AsyncClient
) -> dict:
    item = (
        await supabase.table("product_items")
        .select("vendor_id")
        .eq("id", str(item_id))
        .single()
        .execute()
    )

    if not item.data or item.data["vendor_id"] != str(vendor_id):
        raise HTTPException(403, "Not your product item")

    await (
        supabase.table("product_items")
        .update({"is_deleted": True})
        .eq("id", str(item_id))
        .execute()
    )

    return {"success": True, "message": "Product item deleted (archived)"}


# Initiate payment (single item + quantity)
async def initiate_product_payment(
    data: ProductOrderCreate, customer_info: dict, supabase: AsyncClient
) -> PaymentInitializationResponse:
    try:
        # Fetch the product
        item_resp = (
            await supabase.table("product_items")
            .select(
                "id, vendor_id, price, stock, name, in_stock, sizes, colors, shipping_cost"
            )
            .eq("id", str(data.item_id))
            .single()
            .execute()
        )

        if not item_resp.data or not item_resp.data["in_stock"]:
            raise HTTPException(400, "Product not available or out of stock")

        item = item_resp.data

        if item["stock"] < data.quantity:
            raise HTTPException(400, f"Only {item['stock']} units left in stock")

        # Calculate subtotal
        subtotal = Decimal(str(item["price"])) * data.quantity

        # Delivery fee (from seller profile)
        shipping_cost = item.get("shipping_cost", 0)

        grand_total = subtotal + (shipping_cost if shipping_cost is not None else 0)

        # Generate tx_ref
        tx_ref = f"PRODUCT-{uuid.uuid4().hex[:32].upper()}"

        # Save pending state
        pending_data = {
            "product_name": item["name"],
            "price": safe_numeric_str(item["price"]),
            "customer_id": str(customer_info.get("id")),
            "vendor_id": str(data.vendor_id),
            "item_id": str(data.item_id),
            "quantity": data.quantity,
            "selected_size": data.sizes,
            "selected_color": data.colors,
            "subtotal": safe_numeric_str(subtotal),
            "shipping_cost": safe_numeric_str(shipping_cost),
            "grand_total": safe_numeric_str(grand_total),
            "images": data.images,
            "delivery_option": data.delivery_option,
            "delivery_address": data.delivery_address,
            "additional_info": data.additional_info,
            "tx_ref": tx_ref,
        }
        await save_pending(f"pending_product_{tx_ref}", pending_data)

        return PaymentInitializationResponse(
            tx_ref=tx_ref,
            amount=Decimal(str(grand_total)),
            public_key=settings.FLUTTERWAVE_PUBLIC_KEY,
            currency="NGN",
            receiver_phone=customer_info.get("phone_number"),
            package_name=item["name"],
            customer=PaymentCustomerInfo(
                email=customer_info.get("email"),
                phone_number=customer_info.get("phone_number"),
                full_name=customer_info.get("full_name") or "N/A",
            ),
            customization=PaymentCustomization(
                title="Servipal Delivery",
                description=f"Payment for {item['name']} ({data.quantity} units)",
                logo="https://mohdelivery.s3.us-east-1.amazonaws.com/favion/favicon.ico",
            ),
            message="Ready for payment",
        ).model_dump()

    except Exception as e:
        raise HTTPException(500, f"Product payment initiation failed: {str(e)}")


async def customer_confirm_product_order(
    order_id: UUID, customer_id: UUID, supabase: AsyncClient
) -> dict:
    try:
        order = (
            await supabase.table("product_orders")
            .select("id, buyer_id, vendor_id, grand_total, order_status")
            .eq("id", str(order_id))
            .single()
            .execute()
        )

        if order.data["buyer_id"] != str(customer_id):
            raise HTTPException(403, "Not your order")

        if order.data["order_status"] != "READY":
            raise HTTPException(400, "Order not ready for confirmation")

        tx = (
            await supabase.table("transactions")
            .select("id, amount, to_user_id, status")
            .eq("order_id", str(order_id))
            .single()
            .execute()
        )

        if tx.data["status"] == "RELEASED":
            raise HTTPException(400, "Already confirmed")

        full_amount = tx.data["amount"]
        vendor_id = order.data["vendor_id"]

        # Get commission rate
        # commission_rate = await get_commission_rate("PRODUCT", supabase)
        # seller_amount = full_amount * commission_rate

        # Atomic release: escrow → seller balance (use the same RPC)
        await supabase.rpc(
            "release_order_payment",
            {
                "p_customer_id": str(customer_id),
                "p_vendor_id": str(vendor_id),
                "p_full_amount": full_amount,
            },
        ).execute()

        # Update transaction
        await (
            supabase.table("transactions")
            .update({"status": "RELEASED"})
            .eq("id", tx.data["id"])
            .execute()
        )

        # Update order to COMPLETED
        await (
            supabase.table("product_orders")
            .update({"order_status": "COMPLETED"})
            .eq("id", str(order_id))
            .execute()
        )

        # Stock reduction + total_sold increment happens via trigger (see earlier)

        return {
            "success": True,
            "message": "Order confirmed! Payment released to seller.",
            "order_status": "COMPLETED",
            "amount_released": float(full_amount),
        }

    except Exception as e:
        raise HTTPException(500, f"Confirmation failed: {str(e)}")


async def update_order_status(
    order_id: UUID,
    payload: UpdateOrderStatusRequest,
    current_user: dict,
    supabase: AsyncClient,
):
    try:
        result = await supabase.rpc(
            "update_product_order_status",
            {
                "p_order_id": str(order_id),
                "p_user_id": str(current_user["id"]),
                "p_new_status": payload.new_status,
                "p_cancel_reason": payload.cancel_reason,
            },
        ).execute()

        response = result.data

        if not response:
            raise HTTPException(status_code=500, detail="No response from order update")

        # Notify the other party
        other_user_id = None
        message_map = {
            "SHIPPED": ("Order Shipped", "Your order is on its way!"),
            "DELIVERED": ("Order Delivered", "Your order has been delivered."),
            "COMPLETED": (
                "Order Completed",
                "Order completed. Payment has been released.",
            ),
            "CANCELLED": ("Order Cancelled", "An order has been cancelled."),
            "REJECTED": ("Order Rejected", "The buyer has rejected the order."),
            "RETURNED": ("Item Returned", "The item has been marked as returned."),
            "DISPUTED": ("Order Disputed", "A dispute has been raised on your order."),
        }

        title, body = message_map.get(
            payload.new_status, ("Order Update", "Your order status has changed.")
        )

        # Notify the other party
        order = (
            await supabase.table("product_orders")
            .select("customer_id, vendor_id")
            .eq("id", str(order_id))
            .single()
            .execute()
        )

        if order.data:
            other_user_id = (
                order.data["vendor_id"]
                if str(current_user["id"]) == order.data["customer_id"]
                else order.data["customer_id"]
            )
            await notify_user(
                user_id=other_user_id,
                title=title,
                body=body,
                data={
                    "order_id": str(order_id),
                    "type": "ORDER_STATUS_UPDATE",
                    "new_status": payload.new_status,
                },
                supabase=supabase,
            )

        logger.info(
            "order_status_updated",
            order_id=str(order_id),
            new_status=payload.new_status,
            updated_by=str(current_user["id"]),
        )

        return response

    except APIError as e:
        logger.error(
            "order_status_update_failed",
            order_id=str(order_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=400, detail="Invalid status transition or input"
        )


async def vendor_mark_product_ready(
    order_id: UUID, vendor_id: UUID, supabase: AsyncClient
) -> ProductVendorMarkReadyResponse:
    """
    Seller marks the product order as ready for pickup or delivery.
    """
    try:
        # 1. Fetch order
        order_resp = (
            await supabase.table("product_orders")
            .select("id, vendor_id, order_status")
            .eq("id", str(order_id))
            .single()
            .execute()
        )

        if not order_resp.data:
            raise HTTPException(404, "Product order not found")

        order = order_resp.data

        # 2. Validation
        if order["vendor_id"] != str(vendor_id):
            raise HTTPException(403, "This is not your order")

        if order["order_status"] != "ACCEPTED":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot mark as ready. Current status: {order['order_status']}",
            )

        # 3. Update to READY
        await (
            supabase.table("product_orders")
            .update({"order_status": "READY"})
            .eq("id", str(order_id))
            .execute()
        )

        return ProductVendorMarkReadyResponse(
            order_id=order_id, message="Order marked as ready for pickup/delivery!"
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(500, f"Failed to mark ready: {str(e)}")


def safe_numeric_str(val):
    if val is None:
        return "0"
    try:
        return str(Decimal(str(val)))
    except Exception:
        return "0"
