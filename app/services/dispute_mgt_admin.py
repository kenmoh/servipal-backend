import math
from uuid import UUID
from supabase import AsyncClient
from fastapi import HTTPException, status
from app.schemas.dispute_schema import (
    DisputeResponse,
    UpdateDisputeStatusRequest,
)
from app.services.audit_service import log_admin_action
from datetime import datetime, timezone


# async def list_disputes(
#     supabase: AsyncClient,
#     filters: DisputeFilters,
#     caller_id: UUID,           
#     page: int = 1,
#     page_size: int = 20,
# ) :
#     result = supabase.rpc(
#         "admin_list_disputes",
#         {
#             "p_caller_id":     str(caller_id), 
#             "p_status":        filters.status,
#             "p_order_type":    filters.order_type,
#             "p_initiator_id":  str(filters.initiator_id) if filters.initiator_id else None,
#             "p_respondent_id": str(filters.respondent_id) if filters.respondent_id else None,
#             "p_date_from":     filters.date_from.isoformat() if filters.date_from else None,
#             "p_date_to":       filters.date_to.isoformat() if filters.date_to else None,
#             "p_search":        filters.search,
#             "p_page":          page,
#             "p_page_size":     page_size,
#         },
#     ).execute()

#     rows = result.data or []
#     total = rows[0]["total_count"] if rows else 0

#     return (
#         data=[DisputeSummary(**r) for r in rows],
#         meta=PaginationMeta(
#             total=total,
#             page=page,
#             page_size=page_size,
#             total_pages=math.ceil(total / page_size) if total else 0,
#         ),
#     )


# async def get_dispute(
#     supabase: AsyncClient,
#     dispute_id: UUID,
#     caller_id: UUID,               # ← required now
# ) -> DisputeResponse:
#     result = supabase.rpc(
#         "admin_get_dispute_detail",
#         {
#             "p_dispute_id": str(dispute_id),
#             "p_caller_id":  str(caller_id),   # ← add
#         },
#     ).execute()

#     if not result.data:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dispute {dispute_id} not found")

#     row = result.data[0]

#     def _party(data: dict | None) -> DisputePartySnippet | None:
#         return DisputePartySnippet(**data) if data else None

#     def _messages(raw: list | None) -> list[DisputeMessageItem]:
#         if not raw:
#             return []
#         return [
#             DisputeMessageItem(
#                 **{k: v for k, v in m.items() if k != "sender"},
#                 sender=_party(m.get("sender")),
#             )
#             for m in raw
#         ]

#     return DisputeResponse(
#         **{k: v for k, v in row.items() if k not in ("initiator", "respondent", "resolved_by", "messages")},
#         initiator=_party(row.get("initiator")),
#         respondent=_party(row.get("respondent")),
#         resolved_by=_party(row.get("resolved_by")),
#         messages=_messages(row.get("messages")),
#     )


# async def add_dispute_message(
#     supabase: AsyncClient,
#     dispute_id: UUID,
#     actor_id: UUID,
#     payload: AddDisputeMessageRequest,
# ) -> DisputeMessageResponse:
#     check = supabase.table("disputes").select("id").eq("id", str(dispute_id)).execute()
#     if not check.data:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dispute {dispute_id} not found")

#     result = supabase.table("dispute_messages").insert({
#         "dispute_id":   str(dispute_id),
#         "sender_id":    str(actor_id),
#         "message_text": payload.message_text,
#         "attachments":  payload.attachments,
#     }).execute()

#     return DisputeMessageResponse(**result.data[0])


async def update_dispute_status(
    supabase: AsyncClient,
    dispute_id: UUID,
    actor_id: UUID,
    payload: UpdateDisputeStatusRequest,
) -> DisputeResponse:
    check = supabase.table("disputes").select("id, status").eq("id", str(dispute_id)).single().execute()
    if not check.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dispute {dispute_id} not found")

    old_status = check.data["status"]
    update_data: dict = {"status": payload.status}

    if payload.resolution_notes:
        update_data["resolution_notes"] = payload.resolution_notes
    if payload.status in ("RESOLVED", "CLOSED"):
        update_data["resolved_by_id"] = str(actor_id)
        update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()

    supabase.table("disputes").update(update_data).eq("id", str(dispute_id)).execute()

    await log_admin_action(
        supabase,
        action="UPDATE_DISPUTE_STATUS",
        entity_type="disputes",
        entity_id=dispute_id,
        actor_id=actor_id,
        old_value={"status": old_status},
        new_value={"status": payload.status, "resolution_notes": payload.resolution_notes},
    )

    # Pass actor_id so the detail fetch also marks admin as read
    return await get_dispute(supabase, dispute_id, caller_id=actor_id)