# Admin Cache Implementation - Quick Start Guide

## What Was Added

### 1. Core Caching System
- **File**: `app/utils/cache_manager.py`
- **Features**:
  - Redis-backed caching with configurable TTL
  - Pydantic model serialization/deserialization
  - Pattern-based cache invalidation
  - Error handling and fallback to fresh data

### 2. Cache Invalidation Endpoints
- **File**: `app/routes/cache_admin.py`
- **Endpoints**:
  - `POST /api/v1/admin/cache/invalidate` - Invalidate specific caches
  - `GET /api/v1/admin/cache/status` - Check cache health

### 3. Updated Admin Routes
- **Files Modified**:
  - `app/routes/delivery_order_mgt_admin_routes.py`
  - `app/routes/restaurant_order_mgt_admin_routes.py`
- **Changes**: Added automatic caching to list and detail endpoints

## Testing the Implementation

### 1. Start the App
```bash
source .venv/Scripts/activate
python -m uvicorn app.main:app --reload
```

### 2. Test Cache Status
```bash
curl -X GET http://localhost:8000/api/v1/admin/cache/status \
  -H "Authorization: Bearer <your_admin_token>"
```

Expected response:
```json
{
  "enabled": true,
  "backend": "redis",
  "healthy": true,
  "message": "Cache backend is operational"
}
```

### 3. Test Cached Endpoint (First Request - Cache Miss)
```bash
curl -X GET "http://localhost:8000/api/v1/delivery-orders?page=1&page_size=20" \
  -H "Authorization: Bearer <your_admin_token>"

# Check response time (should be ~500-800ms from DB)
```

### 4. Test Same Endpoint Again (Cache Hit)
```bash
curl -X GET "http://localhost:8000/api/v1/delivery-orders?page=1&page_size=20" \
  -H "Authorization: Bearer <your_admin_token>"

# Check response time (should be ~5-20ms from Redis)
```

### 5. Test Cache Invalidation
```bash
curl -X POST http://localhost:8000/api/v1/admin/cache/invalidate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_admin_token>" \
  -d '{
    "target": "delivery_orders"
  }'
```

Expected response:
```json
{
  "status": "success",
  "message": "Delivery orders cache invalidated (all)",
  "count_invalidated": 12
}
```

### 6. Test After Invalidation (Cache Miss Again)
```bash
curl -X GET "http://localhost:8000/api/v1/delivery-orders?page=1&page_size=20" \
  -H "Authorization: Bearer <your_admin_token>"

# Check response time (should be back to ~500-800ms from DB)
```

## How to Extend Caching to Other Admin Routes

### Step 1: Add cache key generator in `app/utils/cache_manager.py`
```python
@staticmethod
def get_my_items_list_key(filters_hash: str, page: int) -> str:
    """Generate cache key for my items list."""
    return f"cache:admin:my_items:list:{filters_hash}:p{page}"

@staticmethod
def get_my_item_detail_key(item_id: str) -> str:
    """Generate cache key for my item detail."""
    return f"cache:admin:my_items:detail:{item_id}"
```

### Step 2: Update the route file
```python
from app.utils.cache_manager import cache_manager, create_filter_hash

@router.get("", response_model=MyItemListResponse)
async def list_items(
    # ... filter parameters ...
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _actor: dict = Depends(require_admin),
):
    # Create filter dict with all parameters
    filters_dict = {
        "status": status,
        "vendor_id": str(vendor_id) if vendor_id else None,
        # ... all other filters ...
    }
    
    # Generate cache key
    cache_key = cache_manager.get_my_items_list_key(
        create_filter_hash(filters_dict), 
        page
    )
    
    # Try to get from cache
    cached = await cache_manager.get_cached(cache_key, MyItemListResponse)
    if cached:
        return cached
    
    # Call service if not cached
    filters = MyItemFilters(
        status=status,
        vendor_id=vendor_id,
        # ... all other filters ...
    )
    result = await my_service.list_items(supabase, filters, page, page_size)
    
    # Cache the result
    await cache_manager.set_cached(cache_key, result, ttl=cache_manager.DEFAULT_LIST_TTL)
    
    return result

@router.get("/{item_id}", response_model=MyItemDetail)
async def get_item(
    item_id: UUID,
    supabase: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    cache_key = cache_manager.get_my_item_detail_key(str(item_id))
    
    # Try cache first
    cached = await cache_manager.get_cached(cache_key, MyItemDetail)
    if cached:
        return cached
    
    # Get from service
    result = await my_service.get_item(supabase, item_id)
    
    # Cache result
    await cache_manager.set_cached(cache_key, result, ttl=cache_manager.DEFAULT_DETAIL_TTL)
    
    return result
```

### Step 3: Update cache invalidation endpoint patterns
Add support in `app/routes/cache_admin.py`:
```python
elif request.target == "my_items":
    pattern = f"cache:admin:my_items:*"
    # ... rest of implementation
```

## Supabase Realtime Integration

### Setup in Your Supabase RLS Function or Client

**Client-side (JavaScript/React):**
```javascript
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(URL, KEY);

// Subscribe to delivery_orders changes
supabase
  .channel('public:delivery_orders')
  .on('postgres_changes', 
    { event: '*', schema: 'public', table: 'delivery_orders' },
    async (payload) => {
      // Call cache invalidation when data changes
      const orderId = payload.new?.id || payload.old?.id;
      
      await fetch(
        'https://yourdomain.com/api/v1/admin/cache/invalidate',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({
            target: 'delivery_orders',
            order_id: orderId
          })
        }
      );
      
      // Refresh the list in UI
      fetchDeliveryOrders();
    }
  )
  .subscribe();
```

## Monitoring Cache Performance

### Check Redis Key Count
```bash
redis-cli keys "cache:admin:*" | wc -l
```

### Get Cache Stats
```bash
redis-cli info stats | grep -E "total_commands_processed|keyspace_hits|keyspace_misses"
```

### Monitor Memory Usage
```bash
redis-cli info memory | grep -E "used_memory|used_memory_human"
```

## Production Deployment Checklist

- [ ] Redis configured with appropriate memory limits
- [ ] Cache TTL values tuned for your data update frequency
- [ ] Supabase realtime listeners configured for all admin tables
- [ ] Admin authentication properly protected on cache invalidation endpoint
- [ ] Cache status endpoint monitored by health checks
- [ ] Logs reviewed for cache serialization errors
- [ ] Load testing done to verify cache hit rates
- [ ] Documentation updated with your specific tables/endpoints
