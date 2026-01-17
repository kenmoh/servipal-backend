import pytest
from uuid import uuid4
from app.services.notification_service import register_fcm_token, send_push_notification
from app.schemas.notification_schemas import FCMTokenRegister

@pytest.mark.asyncio
async def test_register_fcm_token(mock_supabase):
    user_id = uuid4()
    data = FCMTokenRegister(token="token_123", device_type="android")
    
    result = await register_fcm_token(data, user_id, mock_supabase)
    
    assert result.success is True
    
    # Verify DB
    tokens = mock_supabase._data["fcm_tokens"] if "fcm_tokens" in mock_supabase._data else []
    # My mock client doesn't initialize fcm_tokens list in conftest, 
    # but the `table` method auto-initializes it when accessed.
    tokens = mock_supabase._data["fcm_tokens"]
    assert len(tokens) == 1
    assert tokens[0]["token"] == "token_123"
    assert tokens[0]["user_id"] == str(user_id)

@pytest.mark.asyncio
async def test_send_push_notification():
    # This function uses `batch.send()` from `expo_push_notifications`.
    # We MUST mock it.
    with pytest.MonkeyPatch.context() as m:
        # Create a mock batch object
        mock_batch = pytest.MagicMock()
        mock_batch.send.return_value = [{"status": "ok"}]
        
        # Mock PushClient
        mock_client_cls = pytest.MagicMock()
        mock_client_cls.return_value = mock_batch
        
        m.setattr("app.services.notification_service.PushClient", mock_client_cls)
        # Also need PushMessage
        m.setattr("app.services.notification_service.PushMessage", pytest.MagicMock())
        
        success = await send_push_notification("token", "Title", "Body")
        assert success is True
