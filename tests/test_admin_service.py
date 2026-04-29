import pytest
from uuid import uuid4
from datetime import datetime
from app.services.admin_service import list_users, block_unblock_user
from app.schemas.admin_schemas import UserFilterParams, PaginationParams


@pytest.mark.asyncio
async def test_list_users(mock_supabase):
    # Setup users
    await (
        mock_supabase.table("profiles")
        .insert(
            [
                {
                    "id": str(uuid4()),
                    "full_name": "User A",
                    "user_type": "CUSTOMER",
                    "email": "a@example.com",
                    "phone_number": "111",
                    "is_online": False,
                    "is_verified": True,
                    "is_blocked": False,
                    "account_status": "ACTIVE",
                    "created_at": datetime.now().isoformat(),
                    "store_name": None,
                    "business_name": None,
                    "profile_image_url": None,
                    "last_seen_at": None,
                },
                {
                    "id": str(uuid4()),
                    "full_name": "User B",
                    "user_type": "VENDOR",
                    "email": "b@example.com",
                    "phone_number": "222",
                    "is_online": False,
                    "is_verified": True,
                    "is_blocked": False,
                    "account_status": "ACTIVE",
                    "created_at": datetime.now().isoformat(),
                    "store_name": "Shop B",
                    "business_name": "Biz B",
                    "profile_image_url": None,
                    "last_seen_at": None,
                },
                {
                    "id": str(uuid4()),
                    "full_name": "User C",
                    "user_type": "CUSTOMER",
                    "email": "c@example.com",
                    "phone_number": "333",
                    "is_online": False,
                    "is_verified": True,
                    "is_blocked": False,
                    "account_status": "ACTIVE",
                    "created_at": datetime.now().isoformat(),
                    "store_name": None,
                    "business_name": None,
                    "profile_image_url": None,
                    "last_seen_at": None,
                },
            ]
        )
        .execute()
    )

    filters = UserFilterParams(user_type="CUSTOMER")
    pagination = PaginationParams(page=1, page_size=10)

    result = await list_users(
        supabase=mock_supabase,
        user_type=filters.user_type,
        page=pagination.page,
        page_size=pagination.page_size,
    )

    # Check that we got CUSTOMER users
    # Note: list_users returns ProfileListResponse which has 'data', 'meta'
    assert result.meta.total == 2
    assert len(result.data) == 2
    assert all(u.user_type == "CUSTOMER" for u in result.data)


@pytest.mark.asyncio
async def test_block_user(mock_supabase):
    user_id = uuid4()

    # Injected profile
    await (
        mock_supabase.table("profiles")
        .insert(
            {
                "id": str(user_id),
                "is_blocked": False,
                "full_name": "Test User",
                "phone_number": "1234567890",
                "user_type": "CUSTOMER",
                "account_status": "ACTIVE",
                "email": "test@example.com",
                "is_online": False,
                "is_verified": True,
                "created_at": datetime.now().isoformat(),
                "store_name": None,
                "business_name": None,
                "profile_image_url": None,
                "last_seen_at": None,
            }
        )
        .execute()
    )

    # Call block_unblock_user
    # signature: (supabase, target_id, actor_id, reason, actor_type, request=None)
    from app.schemas.user_schemas import UserType
    
    result = await block_unblock_user(
        supabase=mock_supabase,
        target_id=user_id,
        actor_id=uuid4(),
        reason="Spamming",
        actor_type=UserType.ADMIN,
    )

    assert result.is_blocked is True
