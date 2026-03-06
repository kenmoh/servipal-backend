from uuid import UUID
from fastapi import APIRouter, Depends, status
from supabase import AsyncClient
from app.database.supabase import get_supabase_admin_client
from app.dependencies.auth import require_super_admin
from app.schemas.charges_schema import ChargesCreate, ChargesUpdate, ChargesResponse
from app.services.charge_mgt_admin import (
    list_charges, get_charges,
    create_charges, update_charges, delete_charges,
)

router = APIRouter(prefix="/api/v1/charges", tags=["Charges & Commissions"])


@router.get(
    "",
    response_model=list[ChargesResponse],
    summary="List all charges configs (SUPER_ADMIN only)",
)
async def get_all_charges(
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    actor: dict = Depends(require_super_admin),
):
    return await list_charges(supabase)


@router.get(
    "/{charges_id}",
    response_model=ChargesResponse,
    summary="Get a specific charges config (SUPER_ADMIN only)",
)
async def get_one_charges(
    charges_id: UUID,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    actor: dict = Depends(require_super_admin),
):
    return await get_charges(supabase, charges_id)


@router.post(
    "",
    response_model=ChargesResponse,
    status_code=201,
    summary="Create charges config (SUPER_ADMIN only)",
)
async def create_new_charges(
    body: ChargesCreate,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    actor: dict = Depends(require_super_admin),
):
    return await create_charges(supabase, body, UUID(actor["sub"]))


@router.patch(
    "/{charges_id}",
    response_model=ChargesResponse,
    summary="Update charges config (SUPER_ADMIN only)",
)
async def update_existing_charges(
    charges_id: UUID,
    body: ChargesUpdate,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    actor: dict = Depends(require_super_admin),
):
    return await update_charges(supabase, charges_id, body, UUID(actor["sub"]))


@router.delete(
    "/{charges_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete charges config (SUPER_ADMIN only)",
)
async def delete_existing_charges(
    charges_id: UUID,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    actor: dict = Depends(require_super_admin),
):
    await delete_charges(supabase, charges_id, UUID(actor["sub"]))