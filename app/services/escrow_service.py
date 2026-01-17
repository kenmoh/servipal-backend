from fastapi import HTTPException, status
from uuid import UUID
from decimal import Decimal
from datetime import datetime, timedelta
from app.schemas.escrow_schemas import (
    EscrowAgreementCreate,
    EscrowAgreementResponse,
    EscrowAcceptRequest,
    EscrowRejectRequest,
    EscrowCompletionProposal,
    EscrowCompletionVote,
)
from app.utils.commission import get_commission_rate
from app.utils.audit import log_audit_event
from app.config.logging import logger
from supabase import AsyncClient


async def create_escrow_agreement(
    data: EscrowAgreementCreate, initiator_id: UUID, supabase: AsyncClient
) -> EscrowAgreementResponse:
    try:
        commission_rate = await get_commission_rate("ESCROW_AGREEMENT", supabase)
        commission_amount = data.amount * commission_rate
        net_amount = data.amount - commission_amount

        # Validate shares sum to net_amount
        total_shares = sum(
            p.share_amount for p in data.parties if p.role == "RECIPIENT"
        )
        if total_shares != net_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipient shares must sum to net amount after commission",
            )

        # Create agreement
        agreement = (
            await supabase.table("escrow_agreements")
            .insert(
                {
                    "initiator_id": str(initiator_id),
                    "title": data.title,
                    "description": data.description,
                    "amount": Decimal(data.amount),
                    "commission_rate": Decimal(commission_rate),
                    "status": "DRAFT",
                    "terms": data.terms,
                    "expires_at": (datetime.utcnow() + timedelta(days=14)).isoformat()
                    if data.expires_at is None
                    else data.expires_at.isoformat(),
                    "created_at": datetime.utcnow().isoformat(),
                }
            )
            .execute()
        )

        agreement_id = agreement.data[0]["id"]
        invite_code = agreement.data[0]["invite_code"]

        # Add parties
        parties_data: List[dict] = []
        for party in data.parties:
            parties_data.append(
                {
                    "agreement_id": str(agreement_id),
                    "email": party.email,
                    "phone": party.phone,
                    "role": party.role,
                    "share_amount": Decimal(party.share_amount),
                }
            )

        await supabase.table("escrow_agreement_parties").insert(parties_data).execute()

        await log_audit_event(
            supabase,
            entity_type="ESCROW_AGREEMENT",
            entity_id=str(agreement_id),
            action="CREATED",
            actor_id=str(initiator_id),
            actor_type="USER",
            notes=f"Escrow agreement created for ₦{data.amount}",
        )

        return EscrowAgreementResponse(
            id=agreement_id,
            initiator_id=initiator_id,
            title=data.title,
            description=data.description,
            amount=data.amount,
            commission_rate=commission_rate,
            commission_amount=commission_amount,
            net_amount=net_amount,
            status="DRAFT",
            terms=data.terms,
            invite_code=invite_code,
            expires_at=datetime.utcnow() + timedelta(days=14)
            if data.expires_at is None
            else data.expires_at,
            created_at=datetime.utcnow(),
            parties=[p.model_dump() for p in data.parties],
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create: {str(e)}",
        )


async def accept_escrow_agreement(
    agreement_id: UUID, invite_code: str, user_id: UUID, supabase: AsyncClient
) -> dict:
    try:
        party = (
            await supabase.table("escrow_agreement_parties")
            .select("id, agreement_id, user_id, has_accepted")
            .eq("invite_code", invite_code)
            .single()
            .execute()
            .data
        )

        if not party or party["agreement_id"] != str(agreement_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite"
            )

        if party["user_id"] and party["user_id"] != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invite already used"
            )

        # Associate user
        if not party["user_id"]:
            await (
                supabase.table("escrow_agreement_parties")
                .update({"user_id": str(user_id)})
                .eq("id", party["id"])
                .execute()
            )

        # Accept
        await (
            supabase.table("escrow_agreement_parties")
            .update(
                {"has_accepted": True, "accepted_at": datetime.utcnow().isoformat()}
            )
            .eq("id", party["id"])
            .execute()
        )

        # Check if all accepted
        pending = (
            await supabase.table("escrow_agreement_parties")
            .select("id")
            .eq("agreement_id", str(agreement_id))
            .eq("has_accepted", False)
            .execute()
        )

        if not pending.data:
            await (
                supabase.table("escrow_agreements")
                .update({"status": "READY_FOR_FUNDING"})
                .eq("id", str(agreement_id))
                .execute()
            )

        return {
            "success": True,
            "message": "Accepted. Waiting for others."
            if pending.data
            else "All accepted - ready to fund",
        }

    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Acceptance failed: {str(e)}"
        )


async def reject_escrow_agreement(
    agreement_id: UUID,
    invite_code: str,
    user_id: UUID,
    data: EscrowRejectRequest,
    supabase: AsyncClient,
) -> dict:
    try:
        party = (
            await supabase.table("escrow_agreement_parties")
            .select("id, agreement_id, user_id")
            .eq("invite_code", invite_code)
            .single()
            .execute()
            .data
        )

        if not party or party["agreement_id"] != str(agreement_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invite"
            )

        if party["user_id"] != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not your invite"
            )

        agreement = (
            await supabase.table("escrow_agreements")
            .select("status, initiator_id")
            .eq("id", str(agreement_id))
            .single()
            .execute()
            .data
        )

        if agreement["status"] not in ("DRAFT", "PENDING_ACCEPTANCE"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot reject anymore"
            )

        # Mark rejection
        await (
            supabase.table("escrow_agreement_parties")
            .update({"has_accepted": False, "accepted_at": None, "notes": data.reason})
            .eq("id", party["id"])
            .execute()
        )

        # Cancel agreement
        await (
            supabase.table("escrow_agreements")
            .update(
                {
                    "status": "CANCELLED",
                    "cancelled_at": datetime.utcnow().isoformat(),
                    "cancelled_reason": f"Rejected by party: {data.reason}",
                }
            )
            .eq("id", str(agreement_id))
            .execute()
        )

        # Refund if funded
        if agreement["status"] == "FUNDED":
            agreement_details = (
                await supabase.table("escrow_agreements")
                .select("amount, commission_amount, initiator_id")
                .eq("id", str(agreement_id))
                .single()
                .execute()
                .data
            )

            full_amount = Decimal(str(agreement_details["amount"]))
            commission_amount = Decimal(str(agreement_details["commission_amount"]))
            initiator_id = agreement_details["initiator_id"]

            await supabase.rpc(
                "update_wallet_balance",
                {
                    "p_user_id": str(initiator_id),
                    "p_delta": full_amount - commission_amount,
                    "p_field": "balance",
                },
            ).execute()

            await supabase.rpc(
                "update_wallet_balance",
                {
                    "p_user_id": str(initiator_id),
                    "p_delta": -(full_amount - commission_amount),
                    "p_field": "escrow_balance",
                },
            ).execute()

        return {"success": True, "message": "Rejected and cancelled"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rejection failed: {str(e)}",
        )


async def fund_escrow_agreement(
    agreement_id: UUID, initiator_id: UUID, supabase: AsyncClient
) -> dict:
    try:
        agreement = (
            await supabase.table("escrow_agreements")
            .select("amount, status, initiator_id")
            .eq("id", str(agreement_id))
            .single()
            .execute()
            .data
        )

        if not agreement:
            raise HTTPException(404, "Not found")

        if agreement["initiator_id"] != str(initiator_id):
            raise HTTPException(403, "Not initiator")

        if agreement["status"] != "READY_FOR_FUNDING":
            raise HTTPException(400, f"Cannot fund - status: {agreement['status']}")

        full_amount = Decimal(str(agreement["amount"]))

        await supabase.rpc(
            "update_wallet_balance",
            {
                "p_user_id": str(initiator_id),
                "p_delta": -full_amount,
                "p_field": "balance",
            },
        ).execute()

        await supabase.rpc(
            "update_wallet_balance",
            {
                "p_user_id": str(initiator_id),
                "p_delta": full_amount,
                "p_field": "escrow_balance",
            },
        ).execute()

        await (
            supabase.table("escrow_agreements")
            .update({"status": "FUNDED", "funded_at": datetime.utcnow().isoformat()})
            .eq("id", str(agreement_id))
            .execute()
        )

        return {"success": True, "message": "Funded", "status": "FUNDED"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Funding failed: {str(e)}",
        )


async def propose_escrow_completion(
    agreement_id: UUID,
    user_id: UUID,
    data: EscrowCompletionProposal,
    supabase: AsyncClient,
) -> dict:
    try:
        is_party = (
            await supabase.table("escrow_agreement_parties")
            .select("id")
            .eq("agreement_id", str(agreement_id))
            .eq("user_id", str(user_id))
            .single()
            .execute()
            .data
        )

        if not is_party:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not a party"
            )

        agreement = (
            await supabase.table("escrow_agreements")
            .select("status")
            .eq("id", str(agreement_id))
            .single()
            .execute()
            .data
        )

        if agreement["status"] != "IN_PROGRESS":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Not in progress"
            )

        await (
            supabase.table("escrow_completion_proposals")
            .insert(
                {
                    "agreement_id": str(agreement_id),
                    "proposer_id": str(user_id),
                    "evidence_urls": data.evidence_urls,
                    "notes": data.notes,
                    "proposed_at": datetime.utcnow().isoformat(),
                    "expires_at": (datetime.utcnow() + timedelta(days=14)).isoformat(),
                }
            )
            .execute()
        )

        return {"success": True, "message": "Completion proposed. Waiting for votes."}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Proposal failed: {str(e)}",
        )


async def vote_escrow_completion(
    proposal_id: UUID, user_id: UUID, data: EscrowCompletionVote, supabase: AsyncClient
) -> dict:
    try:
        proposal = (
            await supabase.table("escrow_completion_proposals")
            .select("agreement_id, proposer_id")
            .eq("id", str(proposal_id))
            .single()
            .execute()
            .data
        )

        if not proposal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found"
            )

        is_party = (
            await supabase.table("escrow_agreement_parties")
            .select("id")
            .eq("agreement_id", str(proposal["agreement_id"]))
            .eq("user_id", str(user_id))
            .single()
            .execute()
            .data
        )

        if not is_party:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not a party"
            )

        # Record vote (simple: update has_confirmed_completion)
        await (
            supabase.table("escrow_agreement_parties")
            .update({"has_confirmed_completion": data.confirm})
            .eq("agreement_id", str(proposal["agreement_id"]))
            .eq("user_id", str(user_id))
            .execute()
        )

        # Check if all confirmed
        pending = (
            await supabase.table("escrow_agreement_parties")
            .select("id")
            .eq("agreement_id", str(proposal["agreement_id"]))
            .eq("has_confirmed_completion", False)
            .execute()
        )

        if not pending.data:
            # All confirmed → release
            return await release_escrow_funds(
                proposal["agreement_id"], user_id, supabase
            )

        return {"success": True, "message": "Vote recorded. Waiting for others."}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vote failed: {str(e)}",
        )


async def release_escrow_funds(
    agreement_id: UUID, user_id: UUID, supabase: AsyncClient
) -> dict:
    try:
        agreement = (
            await supabase.table("escrow_agreements")
            .select("status, amount, commission_rate, initiator_id")
            .eq("id", str(agreement_id))
            .single()
            .execute()
            .data
        )

        if not agreement or agreement["status"] != "IN_PROGRESS":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot release")

        full_amount = Decimal(str(agreement["amount"]))
        commission_amount = full_amount * Decimal(str(agreement["commission_rate"]))
        net_amount = full_amount - commission_amount

        recipients = (
            await supabase.table("escrow_agreement_parties")
            .select("user_id, share_amount")
            .eq("agreement_id", str(agreement_id))
            .eq("role", "RECIPIENT")
            .execute()
            .data
        )

        for r in recipients:
            share = Decimal(str(r["share_amount"]))
            await supabase.rpc(
                "update_wallet_balance",
                {
                    "p_user_id": str(agreement["initiator_id"]),
                    "p_delta": -share,
                    "p_field": "escrow_balance",
                },
            ).execute()

            await supabase.rpc(
                "update_wallet_balance",
                {
                    "p_user_id": str(r["user_id"]),
                    "p_delta": share,
                    "p_field": "balance",
                },
            ).execute()

        await (
            supabase.table("platform_commissions")
            .insert(
                {
                    "service_type": "ESCROW_AGREEMENT",
                    "commission_amount": float(commission_amount),
                    "description": f"Commission from escrow {agreement_id}",
                }
            )
            .execute()
        )

        await (
            supabase.table("escrow_agreements")
            .update(
                {"status": "COMPLETED", "completed_at": datetime.utcnow().isoformat()}
            )
            .eq("id", str(agreement_id))
            .execute()
        )

        return {"success": True, "message": "Funds released", "released": net_amount}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Release failed: {str(e)}",
        )
