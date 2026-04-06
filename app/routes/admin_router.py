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
from app.utils.cache_manager import cache_manager, create_filter_hash

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


# ── List all users (any admin role) ──────────────────────────────────────────
@router.get(
    "/users",
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
    filters_dict = {
        "user_type": str(user_type) if user_type else None,
        "account_status": str(account_status) if account_status else None,
        "is_blocked": is_blocked,
        "search": search,
    }
    
    cache_key = cache_manager.get_users_list_key(
        create_filter_hash(filters_dict), page
    )
    
    # Try to get from cache first
    cached = await cache_manager.get_cached(cache_key, ProfileListResponse)
    if cached:
        return cached
    
    result = await admin_service.list_users(
        supabase,
        user_type=user_type,
        account_status=account_status,
        is_blocked=is_blocked,
        search=search,
        page=page,
        page_size=page_size,
    )
    
    # Cache the result
    await cache_manager.set_cached(cache_key, result, ttl=cache_manager.DEFAULT_LIST_TTL)
    
    return result


# ── View user detail (any admin role) ────────────────────────────────────────
@router.get(
    "/users/{user_id}",
    response_model=ProfileDetail,
    summary="Get full profile detail for any user",
)
async def get_user(
    user_id: UUID,
    supabase: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    cache_key = cache_manager.get_user_detail_key(str(user_id))
    
    # Try to get from cache first
    cached = await cache_manager.get_cached(cache_key, ProfileDetail)
    if cached:
        return cached
    
    result = await admin_service.get_user(supabase, user_id)
    
    # Cache the result
    await cache_manager.set_cached(cache_key, result, ttl=cache_manager.DEFAULT_DETAIL_TTL)
    
    return result


# ── Block user (ADMIN or SUPER_ADMIN) ────────────────────────────────────────
@router.patch(
    "/users/{user_id}/block",
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
    db: AsyncClient = Depends(get_supabase_admin_client),
    _actor: dict = Depends(require_admin),
):
    cache_key = cache_manager.get_wallets_list_key(page)
    
    # Try to get from cache first
    cached = await cache_manager.get_cached(cache_key, WalletListResponse)
    if cached:
        return cached
    
    result = await admin_service.list_wallets_with_transactions(
        db, page=page, page_size=page_size
    )
    
    # Cache the result
    await cache_manager.set_cached(cache_key, result, ttl=cache_manager.DEFAULT_LIST_TTL)
    
    return result


@router.get(
    "/wallets/{user_id}",
    response_model=WalletWithTransactions,
    summary="Get a specific user wallet with transactions (any admin role)",
)
async def get_wallet(
    user_id: UUID,
    db: AsyncClient = Depends(get_supabase_admin_client),
    _actor: dict = Depends(require_admin),
):
    cache_key = cache_manager.get_wallet_detail_key(str(user_id))
    
    # Try to get from cache first
    cached = await cache_manager.get_cached(cache_key, WalletWithTransactions)
    if cached:
        return cached
    
    result = await admin_service.get_wallet_with_transactions(db, user_id)
    
    # Cache the result
    await cache_manager.set_cached(cache_key, result, ttl=cache_manager.DEFAULT_DETAIL_TTL)
    
    return result


# Manual user verification for testing purposes
@router.patch(
    "/users/{user_id}/verify",
    summary="Verify a user (ADMIN or SUPER_ADMIN)",
)
async def verify_user(
    user_id: UUID,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    actor: dict = Depends(require_admin_or_super),
):
    await supabase.auth.admin.update_user_by_id({
        "id": str(user_id),
        "email_confirm": True,
    })
    return {
        "message": "User verified successfully",
        "user_id": user_id,
    }

