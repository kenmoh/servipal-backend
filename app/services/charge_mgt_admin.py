from uuid import UUID
from supabase import AsyncClient
from app.schemas.charges_schema import ChargesCreate, ChargesUpdate, ChargesResponse
from fastapi import HTTPException, status
from app.services.audit_service import log_admin_action

TABLE = "charges_and_commissions"


async def list_charges(supabase: AsyncClient) -> list[ChargesResponse]:
    result = (
        await supabase.table(TABLE).select("*").order("created_at", desc=True).execute()
    )
    return [ChargesResponse(**r) for r in result.data]


async def get_charges(supabase: AsyncClient, charges_id: UUID) -> ChargesResponse:
    result = await (
        supabase.table(TABLE).select("*").eq("id", str(charges_id)).single().execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Charges config {charges_id} not found",
        )
    return ChargesResponse(**result.data)


async def create_charges(
    supabase: AsyncClient,
    payload: ChargesCreate,
    actor_id: UUID,
) -> ChargesResponse:
    data = payload.model_dump(mode="json", exclude_none=True)
    result = await supabase.table(TABLE).insert(data).execute()
    new_row = result.data[0]

    await log_admin_action(
        supabase,
        action="CREATE_CHARGES_CONFIG",
        entity_type=TABLE,
        entity_id=UUID(new_row["id"]),
        actor_id=actor_id,
        new_value=data,
    )
    return ChargesResponse(**new_row)


async def update_charges(
    supabase: AsyncClient,
    charges_id: UUID,
    payload: ChargesUpdate,
    actor_id: UUID,
) -> ChargesResponse:
    old = await get_charges(supabase, charges_id)

    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        return old  # nothing to update

    result = await (
        supabase.table(TABLE).update(data).eq("id", str(charges_id)).execute()
    )
    new_row = result.data[0]

    await log_admin_action(
        supabase,
        action="UPDATE_CHARGES_CONFIG",
        entity_type=TABLE,
        entity_id=charges_id,
        actor_id=actor_id,
        old_value=old.model_dump(mode="json", exclude={"created_at", "updated_at"}),
        new_value=data,
    )
    return ChargesResponse(**new_row)


async def delete_charges(
    db: AsyncClient,
    charges_id: UUID,
    actor_id: UUID,
) -> None:
    old = await get_charges(db, charges_id)  # raises 404 if not found

    db.table(TABLE).delete().eq("id", str(charges_id)).execute()

    await log_admin_action(
        db,
        action="DELETE_CHARGES_CONFIG",
        entity_type=TABLE,
        entity_id=charges_id,
        actor_id=actor_id,
        old_value=old.model_dump(mode="json", exclude={"created_at", "updated_at"}),
    )
