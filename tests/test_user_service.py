import pytest
from uuid import uuid4
from fastapi import HTTPException

from app.services.user_service import (
    create_user_account,
    login_user,
    update_user_profile,
    create_rider_by_dispatch,
    get_user_profile
)
from app.schemas.user_schemas import (
    UserCreate,
    LoginRequest,
    ProfileUpdate,
    RiderCreateByDispatch,
    UserType
)

@pytest.mark.asyncio
async def test_create_user_account(mock_supabase):
    data = UserCreate(
        email="test_signup@example.com",
        password="password123",
        phone="+1234567890",
        user_type=UserType.CUSTOMER,
        full_name="Signup User"
    )
    
    # This calls auth.sign_up -> conftest triggers profile creation -> service fetches profile
    result = await create_user_account(data, mock_supabase)
    
    assert result.user.email == "test_signup@example.com"
    assert result.user.full_name == "Signup User"
    
    # Verify DB
    profiles = mock_supabase._data["profiles"]
    assert len(profiles) >= 1
    assert profiles[-1]["email"] == "test_signup@example.com"


@pytest.mark.asyncio
async def test_login_user(mock_supabase):
    email = "login_test@example.com"
    
    # Create user first via fake signup to populate Auth + Profile
    fake_signup = {
        "email": email,
        "password": "pwd",
        "options": {"data": {"full_name": "Login User", "user_type": "CUSTOMER"}}
    }
    await mock_supabase.auth.sign_up(fake_signup)
    
    # Now login
    login_data = LoginRequest(email=email, password="pwd")
    result = await login_user(login_data, mock_supabase)
    
    assert result.access_token == "mock_access_token"
    assert result.user.email == email

@pytest.mark.asyncio
async def test_update_user_profile(mock_supabase):
    user_id = uuid4()
    
    # Setup
    await mock_supabase.table("profiles").insert({
        "id": str(user_id),
        "full_name": "Old Name",
        "user_type": "CUSTOMER",
        "can_pickup_and_dropoff": False
    }).execute()
    
    data = ProfileUpdate(full_name="New Name")
    
    result = await update_user_profile(user_id, data, mock_supabase)
    
    assert result.full_name == "New Name"
    
    # Verify DB
    profiles = mock_supabase._data["profiles"]
    assert profiles[0]["full_name"] == "New Name"

@pytest.mark.asyncio
async def test_create_rider_by_dispatch(mock_supabase):
    dispatch_id = uuid4()
    
    # Setup Dispatch Profile
    await mock_supabase.table("profiles").insert({
        "id": str(dispatch_id),
        "user_type": "DISPATCH",
        "business_name": "Fast Delivery",
        "business_address": "123 St",
        "state": "Lagos"
    }).execute()
    
    data = RiderCreateByDispatch(
        full_name="Rider 1",
        email="rider@fast.com",
        phone="+1112223333",
        bike_number="BK-123"
    )
    
    # We need to act as admin client
    # The service uses `supabase_admin.auth.admin.create_user`
    # And then upserts profile.
    
    result = await create_rider_by_dispatch(
        data, 
        {"id": str(dispatch_id)}, 
        mock_supabase
    )
    
    assert result.full_name == "Rider 1"
    assert result.bike_number == "BK-123"
    
    # Verify DB (Profiles)
    # The service inserts into profiles
    profiles = mock_supabase._data["profiles"]
    rider = next((p for p in profiles if p["full_name"] == "Rider 1"), None)
    assert rider is not None
    assert rider["dispatcher_id"] == str(dispatch_id)
    assert rider["business_name"] == "Fast Delivery" # Inherited
