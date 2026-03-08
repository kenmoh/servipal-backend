from fastapi import HTTPException, status
from pydantic import EmailStr
from redis.asyncio import Redis
from uuid import UUID
from datetime import datetime, timezone
import httpx
from supabase import AsyncClient
from app.config.logging import logger
from typing import Optional
from app.config.config import settings


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


async def get_push_token(user_id: UUID, supabase: AsyncClient) -> Optional[str]:
    """Get single push token for a user (latest registered)"""
    try:
        result = (
            await supabase.table("push_tokens")
            .select("token")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            logger.warning("no_push_token", user_id=user_id)
            return None

        return result.data[0]["token"]

    except Exception as e:
        logger.error("get_push_token_error", user_id=user_id, error=str(e))
        return None

def normalize_nigerian_phone(phone: str) -> str:
    """
    Normalize Nigerian phone numbers to 234XXXXXXXXXX format.
    Handles formats: 23480..., +23490..., 070...
    """
    phone = phone.strip()
    
    # If starts with +234, remove the +
    if phone.startswith("+234"):
        return phone[1:]
    
    # If already starts with 234, return as is
    if phone.startswith("234"):
        return phone
    
    # If starts with 0, replace 0 with 234
    if phone.startswith("0"):
        return "234" + phone[1:]
    
    # Otherwise return as is
    return phone

async def send_otp(name: str, email: EmailStr, phone: str, supabase: AsyncClient, user_id: str) -> str:
    """Send a 6-digit OTP"""
    # Normalize phone number to 234XXXXXXXXXX format
    phone = normalize_nigerian_phone(phone)
    
    payload = {
        "length": 6,
        "send": "true",
        "medium": ['sms'],
        "expiry": 1,
        'customer': {
            "name": name,
            "email": email,
            "phone": phone
        },
        'sender':"SERVIPAL LIMITED"
        }
    headers = {
        "Authorization": f"Bearer {settings.FLW_PROD_SECRET_KEY}",
        "Content-Type": "application/json",
        "accept": "application/json"
    }

    data = await supabase.table("otp").select("phone_verified").eq("user_id", user_id).execute()

    if data.data and data.data[0].get("phone_verified"):
        logger.info("phone_already_verified", email=email, phone=phone)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already verified."
        )


    async with httpx.AsyncClient() as client:
        response = await client.post(
            f'{settings.FLUTTERWAVE_BASE_URL}/otps',
            json=payload,
            headers=headers
        )

        data = response.json()
        if data['status'] != 'success':
            logger.error("otp_send_failed", email=email, phone=phone, status_code=response.status_code, response=response.text)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP. Please try again later."
            )
        
        otp = data['data'][0].get('otp')
        expiry = data['data'][0].get('expiry')

        await supabase.table("otp").insert({
            "user_id": user_id,
            "otp": otp,
            "expires_at": expiry
        }).execute()


async def verify_otp(otp: str, supabase: AsyncClient, user_id: str) -> bool:
    """Verify a 6-digit OTP"""
    
    data = await supabase.table("otp").select("otp, expires_at, phone_verified").eq("user_id", user_id).execute()

    if not data.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OTP not found. Please request a new one."
        )

    record = data.data[0]

    if record.get("phone_verified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already verified."
        )

    # Check expiry
    expires_at = datetime.fromisoformat(record["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one."
        )

    # Check OTP match
    if record.get("otp") != otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP. Please try again."
        )

    # Mark phone as verified
    await supabase.table("otp").update({
        "phone_verified": True
    }).eq("user_id", user_id).execute()

    # Activate user account
    await supabase.table("profiles").update({
        "account_status": 'ACTIVE'
    }).eq("id", user_id).execute()

    logger.info("phone_verified", user_id=user_id)
    return True

