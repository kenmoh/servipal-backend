from fastapi import APIRouter, Depends, Query, Request
from supabase import AsyncClient
from app.database.supabase import get_supabase_admin_client
from app.dependencies.auth import require_admin
from app.schemas.admin_schemas import ContactListResponse, Contact, PaginationMeta
import math

router = APIRouter(prefix="/api/v1/admin/contacts", tags=["Admin Contacts"])


@router.get(
    "/",
    response_model=ContactListResponse,
    summary="List contact submissions with optional filters",
)
async def list_contacts(
    category: str | None = Query(None),
    search: str | None = Query(None, description="Search by name, email, or subject"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    _actor: dict = Depends(require_admin),
):
    """
    Fetch all contact submissions from the 'contacts' table via the admin client.
    Bypasses RLS to ensure admin visibility.
    """
    query = supabase.table("contacts").select("*", count="exact")

    if category:
        query = query.eq("category", category)

    if search:
        query = query.or_(
            f"full_name.ilike.%{search}%,"
            f"email.ilike.%{search}%,"
            f"subject.ilike.%{search}%"
        )

    offset = (page - 1) * page_size
    result = await (
        query.order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )

    total = result.count or 0
    return ContactListResponse(
        data=[Contact(**row) for row in result.data],
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )
