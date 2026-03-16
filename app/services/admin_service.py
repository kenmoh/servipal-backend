import math
from uuid import UUID
from supabase import AsyncClient
from fastapi import Request, HTTPException, status
from app.schemas.user_schemas import UserType
from app.schemas.admin_schemas import (
    ProfileDetail,
    ProfileSummary,
    ProfileListResponse,
    PaginationMeta,
    ManagementUserCreate,
    WalletWithTransactions,
    WalletListResponse,
    TransactionItem,
)
from app.schemas.admin_schemas import AccountStatus
from app.services.audit_service import log_admin_action

PROFILES_TABLE = "profiles"
MANAGEMENT_ROLES = {UserType.ADMIN, UserType.MODERATOR}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row_to_summary(row: dict) -> ProfileSummary:
    return ProfileSummary(**row)


def _row_to_detail(row: dict) -> ProfileDetail:
    return ProfileDetail(**row)


async def _fetch_profile_or_404(supabase: AsyncClient, user_id: UUID) -> dict:
    result = (
        await supabase.table(PROFILES_TABLE)
        .select("*")
        .eq("id", str(user_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User {user_id} not found"
        )
    return result.data


# ── List users ────────────────────────────────────────────────────────────────


async def list_users(
    supabase: AsyncClient,
    *,
    user_type: UserType | None = None,
    account_status: AccountStatus | None = None,
    is_blocked: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> ProfileListResponse:
    query = await supabase.table(PROFILES_TABLE).select("*", count="exact")

    if user_type:
        query = query.eq("user_type", user_type.value)
    if account_status:
        query = query.eq("account_status", account_status.value)
    if is_blocked is not None:
        query = query.eq("is_blocked", is_blocked)
    if search:
        query = query.or_(
            f"full_name.ilike.%{search}%,"
            f"email.ilike.%{search}%,"
            f"phone_number.ilike.%{search}%"
        )

    offset = (page - 1) * page_size
    result = (
        query.order("created_at", desc=True)
        .range(offset, offset + page_size - 1)
        .execute()
    )
    total = result.count or 0
    return ProfileListResponse(
        data=[_row_to_summary(r) for r in result.data],
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )


# ── Get single user ───────────────────────────────────────────────────────────


async def get_user(supabase: AsyncClient, user_id: UUID) -> ProfileDetail:
    row = await _fetch_profile_or_404(supabase, user_id)
    return _row_to_detail(row)


# ── Block / Unblock ───────────────────────────────────────────────────────────
async def toggle_block(
    supabase: AsyncClient,
    target_id: UUID,
    actor_id: UUID,
    reason: str,
    actor_type: UserType,
    request: Request | None = None,
) -> ProfileDetail:
    old_row = await _fetch_profile_or_404(supabase, target_id)
    new_blocked = not old_row["is_blocked"]

    result = (
        supabase.table(PROFILES_TABLE)
        .update({"is_blocked": new_blocked, "reason": reason})
        .eq("id", str(target_id))
        .execute()
    )
    action = "BLOCK_USER" if new_blocked else "UNBLOCK_USER"
    await log_admin_action(
        supabase=supabase,
        action=action,
        actor_type=actor_type,
        old_value={"is_blocked": old_row["is_blocked"]},
        new_value={"is_blocked": new_blocked},
        entity_type="profiles",
        entity_id=target_id,
        actor_id=actor_id,
        notes=reason,
        request=request,
    )
    return _row_to_detail(result.data[0])


async def block_unblock_user(
    supabase: AsyncClient,
    target_id: UUID,
    actor_id: UUID,
    reason: str,
    actor_type: UserType,
    request: Request | None = None,
) -> ProfileDetail:
    return await toggle_block(
        supabase=supabase,
        target_id=target_id,
        actor_id=actor_id,
        reason=reason,
        actor_type=actor_type,
        request=request,
    )

# ── Create management user (SUPER_ADMIN only) ─────────────────────────────────


async def create_management_user(
    supabase: AsyncClient,
    payload: ManagementUserCreate,
    actor_id: UUID,
    request: Request | None = None,
) -> ProfileDetail:
    if payload.user_type not in MANAGEMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_type must be ADMIN or MODERATOR",
        )

    # 1. Create auth user via Supabase Admin API
    auth_response = await supabase.auth.admin.create_user(
        {
            "email": payload.email,
            "password": payload.password,
            "email_confirm": True,
        }
    )
    if not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to create auth user"
        )

    new_uid = auth_response.user.id

    # 2. Upsert the profile row (trigger handle_new_profile_wallet fires on insert)
    profile_data = {
        "id": str(new_uid),
        "email": payload.email,
        "phone_number": payload.phone_number,
        "full_name": payload.full_name,
        "user_type": payload.user_type.value,
        "account_status": AccountStatus.ACTIVE.value,
        "is_verified": True,
    }
    result = supabase.table(PROFILES_TABLE).upsert(profile_data).execute()
    new_row = result.data[0]

    await log_admin_action(
        supabase,
        action="CREATE_MANAGEMENT_USER",
        entity_type="profiles",
        entity_id=UUID(new_uid),
        actor_id=actor_id,
        new_value={
            "email": payload.email,
            "user_type": payload.user_type.value,
            "full_name": payload.full_name,
        },
        notes=f"Management user created with role {payload.user_type.value}",
        request=request,
    )
    return _row_to_detail(new_row)


# ── Auth: admin login (via Supabase) ─────────────────────────────────────────


async def admin_login(supabase: AsyncClient, email: str, password: str) -> dict:
    """
    Authenticates the user against Supabase, then verifies they hold
    a management role before issuing the internal JWT.
    """
    auth_resp = await supabase.auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    if not auth_resp.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credentials"
        )

    uid = auth_resp.user.id
    profile_result = (
        supabase.table(PROFILES_TABLE).select("*").eq("id", str(uid)).single().execute()
    )
    if not profile_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found"
        )

    profile = profile_result.data
    if profile["user_type"] not in [
        r.value for r in [UserType.ADMIN, UserType.MODERATOR, UserType.SUPER_ADMIN]
    ]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient role",
        )

    if profile.get("is_blocked"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked"
        )

    return profile


# ---------------------------- WALLET MANAGEMENT (via rpc) ----------------------------


async def get_wallet_with_transactions(
    supabase: AsyncClient, user_id: UUID
) -> WalletWithTransactions:
    """
    Fetch a single wallet + its transactions via RPC.
    Uses admin_get_wallet_with_transactions(p_user_id).
    """
    result = await supabase.rpc(
        "admin_get_wallet_with_transactions",
        {"p_user_id": str(user_id)},
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet not found for user {user_id}",
        )

    row = result.data[0]
    transactions = [TransactionItem(**tx) for tx in (row.get("transactions") or [])]

    return WalletWithTransactions(
        id=row["wallet_id"],
        user_id=row["user_id"],
        balance=row["balance"],
        escrow_balance=row["escrow_balance"],
        created_at=row["wallet_created_at"],
        updated_at=row.get("wallet_updated_at"),
        transactions=transactions,
    )


async def list_wallets_with_transactions(
    supabase: AsyncClient,
    page: int = 1,
    page_size: int = 25,
) -> WalletListResponse:
    """
    Paginated list of wallets + their transactions via RPC.
    Uses admin_list_wallets_with_transactions(p_page, p_page_size).
    """
    result = await supabase.rpc(
        "admin_list_wallets_with_transactions",
        {"p_page": page, "p_page_size": page_size},
    ).execute()

    if not result.data:
        return WalletListResponse(
            data=[],
            meta=PaginationMeta(total=0, page=page, page_size=page_size, total_pages=0),
        )

    total = result.data[0].get("total_count", 0)
    wallets: list[WalletWithTransactions] = []

    for row in result.data:
        transactions = [TransactionItem(**tx) for tx in (row.get("transactions") or [])]
        wallets.append(
            WalletWithTransactions(
                id=row["wallet_id"],
                user_id=row["user_id"],
                balance=row["balance"],
                escrow_balance=row["escrow_balance"],
                created_at=row["wallet_created_at"],
                updated_at=row.get("wallet_updated_at"),
                transactions=transactions,
            )
        )

    return WalletListResponse(
        data=wallets,
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )
