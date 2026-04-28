from fastapi import HTTPException, status
from uuid import UUID
from decimal import Decimal
from typing import List
from datetime import datetime
from supabase import AsyncClient
from app.schemas.dispute_schema import (
    DisputeCreate,
    DisputeMessageCreate,
    DisputeResolve,
    DisputeResponse,
    DisputeMessageResponse,
    # DisputePaginationMeta,
)
from app.utils.audit import log_audit_event
from app.utils.dispute_helpers import (
    get_order,
    update_order_status,
    is_admin,
    refund_escrow,
    release_escrow,
    release_escrow_funds_for_dispute,
    get_escrow_agreement,
)
from app.services.notification_service import notify_user


# ───────────────────────────────────────────────
# Create Dispute (Buyer Only)
# ───────────────────────────────────────────────
async def create_dispute(
    data: DisputeCreate, initiator_id: UUID, supabase: AsyncClient
):
    order = await get_order(data.order_id, data.order_type, supabase)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    if order["status"] not in [
        "COMPLETED",
        "READY",
        "ACCEPTED",
    ]:  # only after the order is active
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cannot open dispute for this order status",
        )

    # Determine respondent (seller/vendor)
    respondent_id = order["seller_id"] or order["vendor_id"]

    dispute_data = {
        "order_id": str(data.order_id),
        "order_type": data.order_type,
        "initiator_id": str(initiator_id),
        "respondent_id": str(respondent_id),
        "reason": data.reason,
        "status": "OPEN",
    }

    resp = await supabase.rpc(
        "create_dispute",
        {
            "p_order_id": data.order_id,
            "p_order_type": data.order_type,
            "p_initiator_id": initiator_id,
            "p_respondent_id": respondent_id,
            "p_reason": data.reason,
        },
    ).execute()
    # Update order with dispute_id
    await update_order_status(
        data.order_id, data.order_type, resp.data[0]["id"], supabase
    )

    await notify_user(
        respondent_id,
        "Dispute Opened",
        "Dispute opened for your order,please respond as soon as possible",
        data={"DISPUTE": "Dispute opened for your order"},
        supabase=supabase,
    )

    # Log audit
    await log_audit_event(
        entity_type="DISPUTE",
        entity_id=resp.data[0]["id"],
        action="OPENED",
        notes=data.reason,
        actor_id=str(initiator_id),
        actor_type="BUYER",
        supabase=supabase,
    )

    return resp.data[0]


# ───────────────────────────────────────────────
# Post Message
# ───────────────────────────────────────────────
async def post_dispute_message(
    dispute_id: UUID,
    data: DisputeMessageCreate,
    sender_id: UUID,
    supabase: AsyncClient,
):
    # Check participant
    dispute = (
        await supabase.table("disputes")
        .select("initiator_id, respondent_id, status")
        .eq("id", str(dispute_id))
        .single()
        .execute()
    )

    if str(sender_id) not in [
        str(dispute.data["initiator_id"]),
        str(dispute.data["respondent_id"]),
    ] and not await is_admin(sender_id, supabase):
        raise HTTPException(403, "You are not part of this dispute")

    if dispute.data["status"] in ["RESOLVED", "CLOSED"]:
        raise HTTPException(400, "Dispute is closed, cannot post new messages")

    message_data = {
        "dispute_id": str(dispute_id),
        "sender_id": str(sender_id),
        "message_text": data.message_text,
        "attachments": data.attachments or [],
    }

    resp = await supabase.table("dispute_messages").insert(message_data).execute()

    # Update dispute updated_at
    await (
        supabase.table("disputes")
        .update({"updated_at": datetime.now()})
        .eq("id", str(dispute_id))
        .execute()
    )

    # Log audit
    await log_audit_event(
        entity_type="DISPUTE_MESSAGE",
        entity_id=resp.data[0]["id"],
        action="POSTED",
        notes="New message in dispute",
        actor_id=str(sender_id),
        actor_type="USER",
        supabase=supabase,
    )

    # Realtime broadcast happens automatically via subscription on frontend

    return resp.data[0]


# ───────────────────────────────────────────────
# Resolve Dispute (Admin Only)
# ───────────────────────────────────────────────
async def resolve_dispute(
    dispute_id: UUID, data: DisputeResolve, admin_id: UUID, supabase: AsyncClient
):
    # Check admin
    if not await is_admin(admin_id, supabase):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can resolve disputes",
        )

    # Fetch dispute + order
    dispute = (
        await supabase.table("disputes")
        .select("order_id, order_type, status, initiator_id, respondent_id")
        .eq("id", str(dispute_id))
        .single()
        .execute()
    )

    if dispute.data["status"] not in ["OPEN", "UNDER_REVIEW", "ESCALATED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dispute not open for resolution",
        )

    # Update status
    await (
        supabase.table("disputes")
        .update(
            {
                "status": "RESOLVED",
                "resolution_notes": data.notes,
                "resolved_by_id": str(admin_id),
                "resolved_at": datetime.now(),
            }
        )
        .eq("id", str(dispute_id))
        .execute()
    )

    # Handle escrow based on resolution
    order = await get_order(
        dispute.data["order_id"], dispute.data["order_type"], supabase
    )
    if dispute.data["order_type"] == "ESCROW_AGREEMENT":
        # For escrow, handle differently
        agreement = await get_escrow_agreement(dispute.data["order_id"], supabase)
        total_amount = Decimal(str(agreement["amount"])) + Decimal(
            str(agreement["commission_amount"])
        )
        net_amount = Decimal(str(agreement["amount"]))

        if data.resolution == "BUYER_FAVOR":
            # Refund to initiator
            await refund_escrow(agreement["initiator_id"], total_amount, supabase)
            await update_order_status(
                order["id"], dispute.data["order_type"], "CANCELLED", supabase
            )
        elif data.resolution == "SELLER_FAVOR":
            # Release funds to recipients
            await release_escrow_funds_for_dispute(order["id"], supabase)
            await update_order_status(
                order["id"], dispute.data["order_type"], "COMPLETED", supabase
            )
    else:
        tx = (
            await supabase.table("transactions")
            .select("id, amount, from_user_id, to_user_id")
            .eq("order_id", order["id"])
            .single()
            .execute()
        )
        amount = tx.data["amount"]

        if data.resolution == "BUYER_FAVOR":
            # Full refund to buyer
            await refund_escrow(tx.data["from_user_id"], amount, supabase)
            await update_order_status(
                order["id"], dispute.data["order_type"], "CANCELLED", supabase
            )

        elif data.resolution == "SELLER_FAVOR":
            # Full release to seller
            await release_escrow(
                tx.data["from_user_id"], tx.data["to_user_id"], amount, supabase
            )
            await update_order_status(
                order["id"], dispute.data["order_type"], "COMPLETED", supabase
            )

        elif data.resolution == "COMPROMISE":
            # Partial refund (add split_amount to data later)
            pass  # Implement split if needed

    # Log audit
    await log_audit_event(
        entity_type="DISPUTE",
        entity_id=str(dispute_id),
        action="RESOLVED",
        notes=data.notes,
        actor_id=str(admin_id),
        actor_type="ADMIN",
        supabase=supabase,
    )

    # Notify participants
    await notify_user(
        dispute.data["initiator_id"],
        "Dispute resolved",
        "Your dispute has been resolved",
        data={"dispute_id": str(dispute_id)},
        supabase=supabase,
    )
    await notify_user(
        dispute.data["respondent_id"],
        "Dispute resolved",
        "Your dispute has been resolved",
        data={"dispute_id": str(dispute_id)},
        supabase=supabase,
    )

    return {"success": True, "message": "Dispute resolved"}


# ───────────────────────────────────────────────
# Get My Disputes
# ───────────────────────────────────────────────
import math

# async def get_disputes(
#     current_user_id: UUID, page: int, page_size: int, supabase: AsyncClient
# ) -> DisputeResponse:
#     """
#     Fetch all disputes where the current user is either the initiator (buyer) or respondent (seller/vendor).
#     Ordered by most recent update. Pagination applied.
#     """
#     try:
#         offset = (page - 1) * page_size

#         query = (
#             supabase.table("disputes")
#             .select("""
#                 id,
#                 order_id,
#                 order_type,
#                 initiator_id,
#                 respondent_id,
#                 dispatch_id,
#                 reason,
#                 status,
#                 resolution_notes,
#                 resolved_by_id,
#                 resolved_at,
#                 last_message_text,
#                 last_message_at,
#                 created_at,
#                 updated_at
#             """, count="exact")
#             .neq("status", "RESOLVED")
#             .neq("status", "CLOSED")
#         )

#         disputes_resp = await (
#             query.order("created_at", desc=True)
#             .range(offset, offset + page_size - 1)
#             .execute()
#         )

#         total = disputes_resp.count or 0
#         disputes = disputes_resp.data or []

#         result = []
#         for d in disputes:
#             count_resp = (
#                 await supabase.table("dispute_messages")
#                 .select("count", count="exact")
#                 .eq("dispute_id", d["id"])
#                 .execute()
#             )

#             dispute_data = DisputeResponse(
#                 id=d["id"],
#                 order_id=d["order_id"],
#                 order_type=d["order_type"],
#                 initiator_id=d["initiator_id"],
#                 respondent_id=d["respondent_id"],
#                 dispatch_id=d.get("dispatch_id"),
#                 reason=d["reason"],
#                 status=d["status"],
#                 resolution_notes=d.get("resolution_notes"),
#                 resolved_by_id=d.get("resolved_by_id"),
#                 resolved_at=d.get("resolved_at"),
#                 last_message_text=d.get("last_message_text"),
#                 last_message_at=d.get("last_message_at"),
#                 created_at=d["created_at"],
#                 updated_at=d["updated_at"],
#                 messages=[],
#             )
#             dispute_data.message_count = count_resp.count or 0  # optional field

#             result.append(dispute_data)

#         meta = DisputePaginationMeta(
#             total=total,
#             page=page,
#             page_size=page_size,
#             total_pages=math.ceil(total / page_size) if total else 0,
#         )

#         return DisputeResponse(data=result, meta=meta)

#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to fetch my disputes: {str(e)}",
#         )


# ───────────────────────────────────────────────
# Get Dispute Detail
# ───────────────────────────────────────────────
async def get_dispute_detail(
    dispute_id: UUID, supabase: AsyncClient
) -> DisputeResponse:
    """
    Fetch a single dispute + its full message thread.
    Only accessible if user is initiator, respondent, or admin/moderator.
    """
    try:
        # Fetch dispute (RLS filters access)
        dispute_resp = (
            await supabase.table("disputes")
            .select("""
                id,
                order_id,
                order_type,
                initiator_id,
                respondent_id,
                dispatch_id,
                reason,
                status,
                resolution_notes,
                resolved_by_id,
                resolved_at,
                last_message_text,
                last_message_at,
                created_at,
                updated_at
            """)
            .eq("id", str(dispute_id))
            .single()
            .execute()
        )

        if not dispute_resp.data:
            raise HTTPException(404, "Dispute not found or you don't have access")

        dispute = dispute_resp.data

        # Fetch all messages (ordered by time)
        messages_resp = (
            await supabase.table("dispute_messages")
            .select("""
                id,
                sender_id,
                message_text,
                attachments,
                created_at
            """)
            .eq("dispute_id", str(dispute_id))
            .order("-created_at")
            .execute()
        )

        messages = [DisputeMessageResponse(**msg) for msg in messages_resp.data or []]

        return DisputeResponse(
            id=dispute["id"],
            order_id=dispute["order_id"],
            order_type=dispute["order_type"],
            initiator_id=dispute["initiator_id"],
            respondent_id=dispute["respondent_id"],
            dispatch_id=dispute.get("dispatch_id"),
            reason=dispute["reason"],
            status=dispute["status"],
            resolution_notes=dispute.get("resolution_notes"),
            resolved_by_id=dispute.get("resolved_by_id"),
            resolved_at=dispute.get("resolved_at"),
            last_message_text=dispute.get("last_message_text"),
            last_message_at=dispute.get("last_message_at"),
            created_at=dispute["created_at"],
            updated_at=dispute["updated_at"],
            messages=messages,
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dispute detail: {str(e)}",
        )
