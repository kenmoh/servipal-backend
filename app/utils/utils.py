from fastapi import HTTPException, status
from redis.asyncio import Redis
from uuid import UUID
from supabase import AsyncClient
from app.config.logging import logger
from typing import Optional


async def check_login_attempts(email: str, redis_client: Redis) -> None:
    """Check and handle failed login attempts"""
    key = f"login_attempts:{email}"
    attempts = await redis_client.get(key)

    if attempts and int(attempts) >= 5:
        # Lock account for 15 minutes after 5 failed attempts
        if not await redis_client.get(f"account_locked:{email}"):
            await redis_client.setex(f"account_locked:{email}", 900, 1)  # 15 minutes
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account temporarily locked. Please try again later.",
        )


async def record_failed_attempt(email: str, redis_client: Redis) -> None:
    """Record failed login attempt"""
    key = f"login_attempts:{email}"
    await redis_client.incr(key)
    await redis_client.expire(key, 900)  # Reset after 15 minutes


async def reset_login_attempts(email: str, redis_client: Redis) -> None:
    """Reset login attempts after successful login"""
    key = f"login_attempts:{email}"
    locked_key = f"account_locked:{email}"
    await redis_client.delete(key)
    await redis_client.delete(locked_key)



async def get_push_token(
    user_id: UUID,
    supabase: AsyncClient
) -> Optional[str]:
    """Get single push token for a user (latest registered)"""
    try:
        result = await supabase.table("push_tokens") \
            .select("token") \
            .eq("user_id", str(user_id)) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        if not result.data:
            logger.warning("no_push_token", user_id=user_id)
            return None
        
        return result.data[0]["token"]
    
    except Exception as e:
        logger.error("get_push_token_error", user_id=user_id, error=str(e))
        return None