import pytest
from uuid import uuid4
from datetime import datetime
from fastapi import HTTPException
from app.services.dispute_service import (
    create_dispute,
    get_my_disputes,
    post_dispute_message,
    resolve_dispute,
    get_dispute_detail,
)
from app.schemas.dispute_schema import (
    DisputeCreate,
    DisputeMessageCreate,
    DisputeResolve,
)


@pytest.mark.asyncio
async def test_create_dispute(mock_supabase):
    initiator_id = uuid4()
    respondent_id = uuid4()
    order_id = uuid4()

    # Setup mock order
    # get_order helper checks delivery_orders, product_orders, etc.
    await (
        mock_supabase.table("delivery_orders")
        .insert(
            {
                "id": str(order_id),
                "status": "COMPLETED",
                "sender_id": str(initiator_id),
                "recipient_id": str(uuid4()),
                "seller_id": str(respondent_id),
                "payment_status": "PAID",
            }
        )
        .execute()
    )

    data = DisputeCreate(
        order_id=order_id,
        order_type="DELIVERY",
        reason="Item missing for over 10 characters",
        attachments=[],
    )

    result = await create_dispute(data, initiator_id, mock_supabase)

    assert result["id"] is not None
    assert result["status"] == "OPEN"

    # Verify DB
    disputes = mock_supabase._data["disputes"]
    assert len(disputes) == 1
    assert disputes[0]["initiator_id"] == str(initiator_id)
    assert disputes[0]["respondent_id"] == str(respondent_id)


@pytest.mark.asyncio
async def test_get_my_disputes(mock_supabase):
    user_id = uuid4()
    other_id = uuid4()

    # Create valid dispute in mock db
    await (
        mock_supabase.table("disputes")
        .insert(
            {
                "id": str(uuid4()),
                "order_id": str(uuid4()),
                "order_type": "FOOD",
                "initiator_id": str(user_id),
                "respondent_id": str(other_id),
                "status": "OPEN",
                "reason": "Something went wrong",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        )
        .execute()
    )

    results = await get_my_disputes(user_id, mock_supabase)

    assert len(results) == 1
    assert results[0].reason == "Something went wrong"


@pytest.mark.asyncio
async def test_post_dispute_message(mock_supabase):
    user_id = uuid4()
    dispute_id = uuid4()

    # Setup dispute
    await (
        mock_supabase.table("disputes")
        .insert(
            {
                "id": str(dispute_id),
                "initiator_id": str(user_id),
                "respondent_id": str(uuid4()),
                "status": "OPEN",
                "order_id": str(uuid4()),
                "order_type": "FOOD",
            }
        )
        .execute()
    )

    msg_data = DisputeMessageCreate(message_text="Hello support", attachments=[])

    result = await post_dispute_message(dispute_id, msg_data, user_id, mock_supabase)

    assert result["id"] is not None
    assert result["message_text"] == "Hello support"


@pytest.mark.asyncio
async def test_get_dispute_detail(mock_supabase):
    dispute_id = uuid4()
    user_id = uuid4()

    await (
        mock_supabase.table("disputes")
        .insert(
            {
                "id": str(dispute_id),
                "initiator_id": str(user_id),
                "respondent_id": str(uuid4()),
                "order_id": str(uuid4()),
                "order_type": "FOOD",
                "status": "OPEN",
                "reason": "Test reason",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        )
        .execute()
    )

    # Add a message
    await (
        mock_supabase.table("dispute_messages")
        .insert(
            {
                "id": str(uuid4()),
                "dispute_id": str(dispute_id),
                "sender_id": str(user_id),
                "message_text": "First message",
                "attachments": [],
                "created_at": datetime.now().isoformat(),
            }
        )
        .execute()
    )

    result = await get_dispute_detail(dispute_id, mock_supabase)

    assert result.id == dispute_id
    assert len(result.messages) == 1
    assert result.messages[0].message_text == "First message"


@pytest.mark.asyncio
async def test_resolve_dispute(mock_supabase):
    admin_id = uuid4()
    dispute_id = uuid4()
    initiator_id = uuid4()
    respondent_id = uuid4()
    order_id = uuid4()

    # Setup dispute
    await (
        mock_supabase.table("disputes")
        .insert(
            {
                "id": str(dispute_id),
                "initiator_id": str(initiator_id),
                "respondent_id": str(respondent_id),
                "status": "OPEN",
                "order_id": str(order_id),
                "order_type": "FOOD",
            }
        )
        .execute()
    )

    # Setup order
    await (
        mock_supabase.table("food_orders")
        .insert(
            {
                "id": str(order_id),
                "status": "ACCEPTED",
                "customer_id": str(initiator_id),
                "vendor_id": str(respondent_id),
                "payment_status": "PAID",
            }
        )
        .execute()
    )

    # Setup transaction
    await (
        mock_supabase.table("transactions")
        .insert(
            {
                "id": str(uuid4()),
                "order_id": str(order_id),
                "from_user_id": str(initiator_id),
                "to_user_id": str(respondent_id),
                "amount": 1000,
                "status": "ESCROW",
            }
        )
        .execute()
    )

    # Mock is_admin to return True
    # In dispute_service: if not is_admin(admin_id, supabase): ...
    # Let's add admin to profiles with specific check if possible or mock the helper
    await (
        mock_supabase.table("profiles")
        .insert({"id": str(admin_id), "user_type": "ADMIN"})
        .execute()
    )

    resolve_data = DisputeResolve(
        resolution="BUYER_FAVOR", notes="Refund processed for valid reason"
    )

    # Note: refund_escrow and release_escrow are RPCs or helpers.
    # Our mock client needs to handle these if called.
    # Actually they are imported helpers in dispute_service.
    # I should probably patch them since they might call other logic.

    with pytest.MonkeyPatch.context() as m:
        from unittest.mock import AsyncMock

        m.setattr("app.services.dispute_service.refund_escrow", AsyncMock())
        m.setattr("app.services.dispute_service.release_escrow", AsyncMock())
        m.setattr("app.services.dispute_service.notify_user", AsyncMock())

        result = await resolve_dispute(
            dispute_id, resolve_data, admin_id, mock_supabase
        )

    assert result["success"] is True

    # Verify DB status update
    dispute = (
        await mock_supabase.table("disputes")
        .select("status")
        .eq("id", str(dispute_id))
        .single()
        .execute()
    ).data
    assert dispute["status"] == "RESOLVED"
