from decimal import Decimal
import math
from uuid import UUID
from fastapi import Request
from supabase import AsyncClient
from app.utils.audit import log_audit_event
from app.schemas.admin_schemas import (
    PaginationMeta,
    AuditLogFilters,
    AuditLogCreate,
    AuditLogEntry,
    AuditLogListResponse,
)

AUDIT_TABLE = "audit_logs"


def _get_client_meta(request: Request | None) -> dict:
    if request is None:
        return {}
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0]
        if forwarded
        else (request.client.host if request.client else None)
    )
    return {
        "ip_address": ip,
        "user_agent": request.headers.get("user-agent"),
    }


async def create_audit_log(
    supabase: AsyncClient,
    payload: AuditLogCreate,
) -> AuditLogEntry:
    """Insert a single audit log row."""
    data = payload.model_dump(mode="json", exclude_none=True)
    # Convert UUID fields to str for supabase-py
    for key in ("entity_id", "actor_id"):
        if key in data and data[key] is not None:
            data[key] = str(data[key])

    result = await supabase.table(AUDIT_TABLE).insert(data).execute()
    return AuditLogEntry(**result.data[0])


async def log_admin_action(
    supabase: AsyncClient,
    *,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor_id: UUID,
    actor_type: str = "ADMIN",
    old_value: dict | None = None,
    new_value: dict | None = None,
    notes: str | None = None,
    request: Request | None = None,
) -> None:
    """Convenience wrapper used by other services to record admin actions."""
    meta = _get_client_meta(request)
    payload = AuditLogCreate(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        actor_type=actor_type,
        old_value=old_value,
        new_value=new_value,
        notes=notes,
        **meta,
    )
    await create_audit_log(supabase, payload)


async def list_audit_logs(
    supabase: AsyncClient,
    filters: AuditLogFilters,
    page: int = 1,
    page_size: int = 20,
) -> list[AuditLogEntry]:
    """List audit logs with optional filters and pagination."""
    query = supabase.table(AUDIT_TABLE).select("*", count="exact")

    if filters.entity_type:
        query = query.eq("entity_type", filters.entity_type)
    if filters.entity_id:
        query = query.eq("entity_id", str(filters.entity_id))
    if filters.action:
        query = query.eq("action", filters.action)
    if filters.actor_id:
        query = query.eq("actor_id", str(filters.actor_id))
    if filters.date_from:
        query = query.gte("created_at", filters.date_from.isoformat())
    if filters.date_to:
        query = query.lte("created_at", filters.date_to.isoformat())

    offset = (page - 1) * page_size
    result = await (
        query.order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    total = result.count or 0
    entries = [AuditLogEntry(**row) for row in result.data]
    return AuditLogListResponse(
        data=entries,
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )
