import pytest
from uuid import uuid4
from app.services.review_service import create_review
from app.schemas.review_schemas import ReviewCreate

@pytest.mark.asyncio
async def test_create_review(mock_supabase):
    reviewer_id = uuid4()
    order_id = uuid4()
    vendor_id = uuid4()
    
    # Setup Order
    await mock_supabase.table("food_orders").insert({
        "id": str(order_id),
        "vendor_id": str(vendor_id)
    }).execute()
    
    data = ReviewCreate(
        item_id=None,
        rating=5,
        comment="Great food!",
        reviewee_type="VENDOR"
    )
    
    result = await create_review(order_id, "FOOD", data, reviewer_id, mock_supabase)
    
    assert result["success"] is True
    
    reviews = mock_supabase._data["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["rating"] == 5
