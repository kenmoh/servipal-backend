from fastapi import APIRouter, Depends, Query
from app.services import escrow_service
from app.schemas.escrow_schemas import EscrowAgreementCreate
from app.dependencies.auth import get_current_profile
from app.database.supabase import get_supabase_client
from supabase import AsyncClient
from uuid import UUID

router = APIRouter(prefix="/api/v1/escrow", tags=["Escrow"])


@router.post("/agreements")
async def create_escrow_agreement(
    data: EscrowAgreementCreate,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.create_escrow_agreement(
        data, current_profile["id"], supabase
    )


@router.post("/agreements/{agreement_id}/accept")
async def accept_escrow_agreement(
    agreement_id: UUID,
    invite_code: str = Query(...),
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.accept_escrow_agreement(
        agreement_id, invite_code, current_profile["id"], supabase
    )


@router.post("/agreements/{agreement_id}/reject")
async def reject_escrow_agreement(
    agreement_id: UUID,
    data: EscrowRejectRequest,
    invite_code: str = Query(...),
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.reject_escrow_agreement(
        agreement_id, invite_code, current_profile["id"], data, supabase
    )


@router.post("/agreements/{agreement_id}/fund")
async def fund_escrow_agreement(
    agreement_id: UUID,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.fund_escrow_agreement(
        agreement_id, current_profile["id"], supabase
    )


@router.post("/agreements/{agreement_id}/release")
async def release_escrow_funds(
    agreement_id: UUID,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.release_escrow_funds(
        agreement_id, current_profile["id"], supabase
    )


@router.post("/agreements/{agreement_id}/reject")
async def reject_escrow_agreement(
    agreement_id: UUID,
    data: EscrowRejectRequest,
    invite_code: str = Query(...),
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.reject_escrow_agreement(
        agreement_id=agreement_id,
        invite_code=invite_code,
        user_id=current_profile["id"],
        data=data,
        supabase=supabase,
    )


@router.post("/agreements/{agreement_id}/fund")
async def fund_escrow_agreement(
    agreement_id: UUID,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.fund_escrow_agreement(
        agreement_id, current_profile["id"], supabase
    )


@router.post("/agreements/{agreement_id}/propose-completion")
async def propose_completion(
    agreement_id: UUID,
    data: EscrowCompletionProposal,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.propose_escrow_completion(
        agreement_id, current_profile["id"], data, supabase
    )


@router.post("/proposals/{proposal_id}/vote")
async def vote_completion(
    proposal_id: UUID,
    data: EscrowCompletionVote,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    return await escrow_service.vote_escrow_completion(
        proposal_id, current_profile["id"], data, supabase
    )
