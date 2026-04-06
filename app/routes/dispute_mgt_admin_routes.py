from __future__ import annotations
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from supabase import AsyncClient
from app.database.supabase import get_supabase_client
from app.dependencies.auth import require_admin, require_admin_or_super
from app.schemas.dispute_mgt_schema import (
    DisputeListResponse, DisputeDetail, DisputeFilters,
    AddDisputeMessageRequest, UpdateDisputeStatusRequest,
    DisputeMessageResponse,
)
from app.services.dispute_mgt_admin import (
    list_disputes, get_dispute,
    add_dispute_message, update_dispute_status,
)

router = APIRouter(prefix="/api/v1/disputes", tags=["Dispute Resolution"])


@router.get("", response_model=DisputeListResponse, summary="List disputes with filters")
async def list_all_disputes(
    status:        str | None = Query(None),
    order_type:    str | None = Query(None),
    initiator_id:  UUID | None = Query(None),
    respondent_id: UUID | None = Query(None),
    date_from:     datetime | None = Query(None),
    date_to:       datetime | None = Query(None),
    search:        str | None = Query(None),
    page:          int = Query(1, ge=1),
    page_size:     int = Query(20, ge=1, le=100),
    supabase: AsyncClient = Depends(get_supabase_client),
    actor: dict = Depends(require_admin),   # ← not _actor
):
    filters = DisputeFilters(
        status=status, order_type=order_type,
        initiator_id=initiator_id, respondent_id=respondent_id,
        date_from=date_from, date_to=date_to, search=search,
    )
    return await list_disputes(
        supabase, filters,
        caller_id=UUID(actor["id"]),       # ← pass caller
        page=page, page_size=page_size,
    )


@router.get("/{dispute_id}", response_model=DisputeDetail, summary="Get dispute detail — auto marks as read")
async def get_dispute_detail(
    dispute_id: UUID,
    supabase: AsyncClient = Depends(get_supabase_client),
    actor: dict = Depends(require_admin),   # ← not _actor
):
    return await get_dispute(supabase, dispute_id, caller_id=UUID(actor["sub"]))


@router.post(
    "/{dispute_id}/messages",
    response_model=DisputeMessageResponse,
    status_code=201,
    summary="Admin joins dispute conversation",
)
async def post_dispute_message(
    dispute_id: UUID,
    body: AddDisputeMessageRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
    actor: dict = Depends(require_admin),
):
    return await add_dispute_message(supabase, dispute_id, UUID(actor["sub"]), body)


@router.patch(
    "/{dispute_id}/status",
    response_model=DisputeDetail,
    summary="Update dispute status (ADMIN or SUPER_ADMIN)",
)
async def patch_dispute_status(
    dispute_id: UUID,
    body: UpdateDisputeStatusRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
    actor: dict = Depends(require_admin_or_super),
):
    return await update_dispute_status(supabase, dispute_id, UUID(actor["sub"]), body)