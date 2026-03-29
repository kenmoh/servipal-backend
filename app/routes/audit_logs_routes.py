from __future__ import annotations
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from supabase import AsyncClient
from app.database.supabase import get_supabase_client
from app.dependencies.auth import require_admin
from app.schemas.admin_schemas import AuditLogListResponse, AuditLogFilters
from app.services.audit_service import list_audit_logs

router = APIRouter(prefix="/api/v1/audit-logs", tags=["Audit Logs"])


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="List audit logs with optional filters (any admin role)",
)
async def get_audit_logs(
    entity_type: str | None = Query(None, description="e.g. profiles, wallets"),
    entity_id: UUID | None = Query(None),
    action: str | None = Query(
        None, description="e.g. BLOCK_USER, CREATE_MANAGEMENT_USER"
    ),
    actor_id: UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    supabase: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    filters = AuditLogFilters(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        date_from=date_from,
        date_to=date_to,
    )
    return await list_audit_logs(supabase, filters, page=page, page_size=page_size)


@router.get(
    "/user/{user_id}",
    response_model=AuditLogListResponse,
    summary="All audit log entries for a specific user",
)
async def get_user_audit_logs(
    user_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    supabase: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    filters = AuditLogFilters(entity_type="profiles", entity_id=user_id)
    return await list_audit_logs(supabase, filters, page=page, page_size=page_size)
