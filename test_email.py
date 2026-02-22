#!/usr/bin/env python
"""Test script to send an email using Supabase."""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from app.database.supabase import create_supabase_admin_client
from app.config.config import settings
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def send_test_email():
    """Send a test email using Supabase Admin API."""
    try:
        # Create an admin client
        supabase = await create_supabase_admin_client()

        # Test email details
        test_email = "moh2stack@hmail.com"

        print(f"Attempting to send test email to: {test_email}")
        print(f"Supabase URL: {settings.SUPABASE_URL}")
        await supabase.auth.reset_password_for_email(test_email)
        print(f"✓ Password reset email sent to: {test_email}")

        # Method 1: Use the Supabase admin API to create a user with email verification
        # This will trigger an email to be sent
        try:
            response = await supabase.auth.admin.create_user(
                {
                    "email": test_email,
                    "password": "TempPassword123!",
                    "email_confirm": False,
                }  # This will trigger a confirmation email
            )
            print(f"✓ User created successfully: {response.user.id}")
            print(f"✓ Confirmation email sent to: {test_email}")
            return True
        except Exception as e:
            if "already exists" in str(e):
                print(f"ℹ User already exists with this email")
                # Try inviting the user instead
                try:
                    response = await supabase.auth.admin.invite_user_by_email(
                        email=test_email
                    )
                    print(f"✓ Invitation email sent to: {test_email}")
                    return True
                except Exception as invite_error:
                    print(f"✗ Failed to send invitation: {invite_error}")
                    return False
            else:
                print(f"✗ Error creating user: {e}")
                return False

    except Exception as e:
        print(f"✗ Error initializing Supabase client: {e}")
        return False


async def main():
    """Run email tests."""
    print("=" * 60)
    print("Supabase Email Testing")
    print("=" * 60)

    # Test 1: Send confirmation email (new user)
    print("\n[Test 1] Sending confirmation email (user signup)...")
    success1 = await send_test_email()

    print("\n" + "=" * 60)
    if success1:
        print("✓ Email test completed successfully!")
    else:
        print("✗ Email tests failed. Check your Supabase configuration.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
