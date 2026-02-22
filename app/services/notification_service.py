from uuid import UUID
from supabase import AsyncClient
from fastapi import HTTPException
from app.schemas.notification_schemas import *
from exponent_server_sdk import (
    DeviceNotRegisteredError,
    PushClient,
    PushMessage,
    PushServerError,
    PushTicketError,
)
from requests.exceptions import ConnectionError, HTTPError
from app.config.logging import logger
from datetime import datetime
from app.utils.utils import get_push_token


# ───────────────────────────────────────────────
# Sending Notifications
# ───────────────────────────────────────────────
async def send_push_notification(
    token: str, title: str, body: str, data: dict = None
) -> bool:
    """
    Sends a push notification using Expo's server SDK.
    Args
        token (str): The push token to send the notification to
        title (str): Notification title
        body (str): Notification body
        data (dict): Additional data to send
    Returns
        bool: True if the notification was sent successfully
    """
    try:
        response = PushClient().publish(
            PushMessage(to=token, title=title, body=body, data=data)
        )
    except PushServerError as exc:
        # Encountered some generic error from the Expo push service
        logger.error(
            "push_notification_server_error",
            token=token,
            exc=str(exc),
            errors=exc.errors,
            response_data=exc.response_data,
        )
        return False
    except (ConnectionError, HTTPError) as exc:
        # Encountered some generic error from the requests library
        logger.error("push_notification_connection_error", token=token, exc=str(exc))
        return False

    try:
        # We got a response back, but we don't know if it was successful yet.
        # This will raise errors if there are any issues with the response.
        response.validate_response()
        logger.info("push_notification_sent", token=token, title=title)
        return True
    except DeviceNotRegisteredError:
        # Mark the push token as inactive in your database
        logger.warning("push_notification_device_not_registered", token=token)
        # TODO: Consider deleting the token from fcm_tokens table
        return False
    except PushTicketError as exc:
        # Encountered some other error from the Expo push service
        logger.error(
            "push_notification_ticket_error",
            token=token,
            exc=str(exc),
            push_response=exc.push_response._asdict(),
        )
        return False


async def notify_user(
    user_id: str,
    title: str,
    body: str,
    data: dict = None,
    supabase: AsyncClient = None,
) -> bool:
    """
    Helper to fetch a user's push token and send them a notification.
    Returns True if the notification was sent successfully.
    Args
        user_id (UUID): The user to notify
        title (str): Notification title
        body (str): Notification body
        data (dict): Additional data to send
        supabase (AsyncClient): Supabase client instance
    """
    if not supabase:
        from app.database.supabase import create_supabase_admin_client

        supabase = await create_supabase_admin_client()

    token = await get_push_token(user_id, supabase)
    logger.debug("*" * 100)
    logger.info(f"Attempting to send notification to user {user_id} with token {token}")
    if not token:
        logger.debug("push_notification_no_token", user_id=str(user_id))
        return False
    logger.debug("*" * 100)

    return await send_push_notification(token, title, body, data)
