import pytest
from uuid import uuid4
from decimal import Decimal
from fastapi import HTTPException
from app.services.product_service import (
    create_product_item,
    get_product_item,
    get_my_product_items,
    delete_product_item
)
from app.schemas.product_schemas import ProductItemCreate

@pytest.mark.asyncio
async def test_create_product_item(mock_supabase):
    seller_id = uuid4()
    
    data = ProductItemCreate(
        name="T-Shirt",
        description="Cotton",
        price=Decimal("5000.00"),
        stock=10,
        category="CLOTHING",
        images=["url1"]
    )
    
    result = await create_product_item(data, seller_id, mock_supabase)
    
    assert result.name == "T-Shirt"
    assert result.seller_id == str(seller_id)
    assert result.price == Decimal("5000.00")
    
    items = mock_supabase._data["product_items"]
    assert len(items) == 1
    assert items[0]["total_sold"] == 0

@pytest.mark.asyncio
async def test_get_product_item(mock_supabase):
    item_id = uuid4()
    
    await mock_supabase.table("product_items").insert({
        "id": str(item_id),
        "name": "Shoes",
        "price": 10000,
        "is_deleted": False
    }).execute()
    
    result = await get_product_item(item_id, mock_supabase)
    
    assert result.name == "Shoes"

@pytest.mark.asyncio
async def test_delete_product_item(mock_supabase):
    item_id = uuid4()
    seller_id = uuid4()
    
    await mock_supabase.table("product_items").insert({
        "id": str(item_id),
        "seller_id": str(seller_id),
        "is_deleted": False
    }).execute()
    
    result = await delete_product_item(item_id, seller_id, mock_supabase)
    
    assert result["success"] is True
    
    # Verify soft delete
    items = mock_supabase._data["product_items"]
    # Usually delete_product_item sets is_deleted=True
    # My MockQueryBuilder 'update' updates in place
    assert items[0]["is_deleted"] is True
