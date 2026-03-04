from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from supabase import AsyncClient
from app.database.supabase import get_supabase_client, get_supabase_admin_client
from app.dependencies.auth import (
    require_admin,
    require_super_admin,
    require_admin_or_super,
)
from app.schemas.admin_schemas import (
    AccountStatus,
    ProfileDetail,
    ProfileListResponse,
    ManagementUserCreate,
    BlockUserRequest,
    WalletListResponse,
    WalletWithTransactions,
)
from app.schemas.user_schemas import UserType
from app.services import admin_service

router = APIRouter(prefix="/users", tags=["Users"])


# ── List all users (any admin role) ──────────────────────────────────────────
@router.get(
    "",
    response_model=ProfileListResponse,
    summary="List users with optional filters",
)
async def list_users(
    request: Request,
    user_type: UserType | None = Query(None),
    account_status: AccountStatus | None = Query(None),
    is_blocked: bool | None = Query(None),
    search: str | None = Query(None, description="Search by name, email or phone"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    supabase: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    return await admin_service.list_users(
        supabase,
        user_type=user_type,
        account_status=account_status,
        is_blocked=is_blocked,
        search=search,
        page=page,
        page_size=page_size,
    )


# ── View user detail (any admin role) ────────────────────────────────────────
@router.get(
    "/{user_id}",
    response_model=ProfileDetail,
    summary="Get full profile detail for any user",
)
async def get_user(
    user_id: UUID,
    supabase: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    return await admin_service.get_user(supabase, user_id)


# ── Block user (ADMIN or SUPER_ADMIN) ────────────────────────────────────────
@router.patch(
    "/{user_id}/block",
    response_model=ProfileDetail,
    summary="Block a user (ADMIN or SUPER_ADMIN)",
)
async def block_user(
    user_id: UUID,
    body: BlockUserRequest,
    request: Request,
    supabase: AsyncClient = Depends(get_supabase_client),
    actor: dict = Depends(require_admin_or_super),
):
    return await admin_service.toggle_block(
        supabase=supabase,
        user_id=user_id,
        actor_id=UUID(actor["sub"]),
        actor_type=actor["user_type"],
        reason=body.reason,
        request=request,
    )


# ── Create management user (SUPER_ADMIN only) ─────────────────────────────────


@router.post(
    "/management",
    response_model=ProfileDetail,
    status_code=201,
    summary="Create ADMIN or MODERATOR account (SUPER_ADMIN only)",
)
async def create_management_user(
    body: ManagementUserCreate,
    request: Request,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    actor: dict = Depends(require_super_admin),
):
    return await admin_service.create_management_user(
        supabase=supabase, payload=body, actor_id=UUID(actor["sub"]), request=request
    )


# ── View Wallet user (SUPER_ADMIN only) ─────────────────────────────────


@router.get(
    "/wallets",
    response_model=WalletListResponse,
    summary="List all wallets with transactions (any admin role)",
)
async def list_wallets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    return await admin_service.list_wallets_with_transactions(
        db, page=page, page_size=page_size
    )


@router.get(
    "/{user_id}/wallet",
    response_model=WalletWithTransactions,
    summary="Get a specific user wallet with transactions (any admin role)",
)
async def get_wallet(
    user_id: UUID,
    db: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    return await admin_service.get_wallet_with_transactions(db, user_id)
