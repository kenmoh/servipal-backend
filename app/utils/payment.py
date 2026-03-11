from asyncio import streams
import datetime
from decimal import Decimal
import json
import httpx
from fastapi import HTTPException, status
from pydantic import BaseModel
from app.config.config import settings
from app.utils.redis_utils import cache_data, get_cached_data
from app.schemas.bank_schema import BankSchema, AccountDetails, AccountDetailResponse
from app.config.logging import logger

class AuthorizationResponse(BaseModel):

    transfer_reference: str
    transfer_account: str
    transfer_bank: str
    account_expiration: datetime.datetime
    transfer_note: str
    transfer_amount: str
    mode: str
   

class TransferMeta(BaseModel):
    
    authorization: AuthorizationResponse


class InitBankTransfer(BaseModel): 
  status: str
  message:str
  meta: TransferMeta


flutterwave_base_url = settings.FLUTTERWAVE_BASE_URL
servipal_base_url = settings.API_URL
bank_url = f"{flutterwave_base_url}/banks/NG?include_provider_type=1"

CONVENTIONAL_BANK_CODES = {
    "044",    
    "050",   
    "070",   
    "011",   
    "214",   
    "058",    
    "301",    
    "082",   
    "076",    
    "221",   
    "232",    
    "032",   
    "033",   
    "215",    
    "035",   
    "057",   
    "101",    
    "000030",
    "000029", 
    "000031", 
    "000034", 
    "103",    
    "000025", 
    "068",    
    "100", 
    "044"   
    "000036", 
}

async def get_all_banks() -> list[BankSchema]:
    cache_key = "banks_list"
    cached_banks = await get_cached_data(cache_key)

    if cached_banks:
        return json.loads(cached_banks)
    try:
        headers = {"Authorization": f"Bearer {settings.FLW_SECRET_KEY}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(bank_url, headers=headers)
            banks = response.json()["data"]

            sorted_banks = sorted(
                banks,
                key=lambda bank: (
                    0 if bank["code"] in CONVENTIONAL_BANK_CODES else 1, 
                    bank["name"],
                ),
            )

            await cache_data(cache_key, json.dumps(sorted_banks, default=str), 86400)
            return sorted_banks

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to get banks: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get banks: {str(e)}",
        )


# async def get_all_banks() -> list[BankSchema]:
#     cache_key = "banks_list"
#     cached_banks = await get_cached_data(cache_key)

#     if cached_banks:
#         return json.loads(cached_banks)
#     try:
#         headers = {"Authorization": f"Bearer {settings.FLW_SECRET_KEY}"}

#         async with httpx.AsyncClient(timeout=30.0) as client:
#             response = await client.get(bank_url, headers=headers)
#             banks = response.json()["data"]

#             sorted_banks = sorted(banks, key=lambda bank: bank["name"])

#             await cache_data(cache_key, json.dumps(sorted_banks, default=str), 86400)
#             return sorted_banks

#     except httpx.HTTPStatusError as e:
#         raise HTTPException(
#             status_code=status.HTTP_502_BAD_GATEWAY,
#             detail=f"Failed to get banks: {str(e)}",
#         )
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to get banks: {str(e)}",
#         )


async def resolve_account_details(
    data: AccountDetails,
) -> AccountDetailResponse:
    """
    Resolve bank account details using Flutterwave API

    Args:
        account_number: Bank account number
        account_bank: Bank code (e.g., "044" for Access Bank)

    Returns:
        Dict containing account details in format:
        {
            "account_number": "0690000032",
            "account_name": "Pastor Bright"
        }

    Raises:
        httpx.HTTPStatusError: If the API request fails
        httpx.RequestError: If there's a network error
    """

    payload = {"account_number": data.account_number, "account_bank": data.account_bank}

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {settings.FLW_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{flutterwave_base_url}/accounts/resolve",
                json=payload,
                headers=headers,
            )

            response.raise_for_status()

            # Get the raw response
            raw_response = response.json()

            # Extract and flatten the required fields
            if raw_response.get("status") == "success" and "data" in raw_response:
                data = raw_response["data"]

                formatted_response = {
                    "account_number": data["account_number"],
                    "account_name": data["account_name"],
                }
                return formatted_response

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Error response from payment gateway: {e.response.status_code} - {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error occurred: {str(e)}")
            raise


async def verify_transaction_tx_ref(tx_ref: str):
    try:
        headers = {"Authorization": f"Bearer {settings.FLW_SECRET_KEY}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{flutterwave_base_url}/transactions/{tx_ref}/verify",
                # f"{flutterwave_base_url}/transactions/verify_by_reference?tx_ref={tx_ref}",
                headers=headers,
            )
            response_data = response.json()
            return response_data
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Payment gateway error: {e.response.status_code} - {e.response.text}"
        )
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to verify transaction reference: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to verify transaction reference: {str(e)}"
        )
    
async def generate_virtual_account_for_bank_transfer_payment(
    amount: Decimal,
    tx_ref: str,
    customer: dict,
) -> InitBankTransfer:

    payload = {
        "amount": str(amount),
        "email": customer["email"],
        "currency": "NGN",
        "tx_ref": tx_ref,
        "fullname": customer["account_holder_name"],
        "phone_number": customer["phone_number"],
        "meta": {
            "message": f"Pay the sum of NGN {amount} for transaction reference {tx_ref} to SERVIPAL LIMITED"
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.FLW_SECRET_KEY}",
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client: 
            response = await client.post(
                f"{settings.FLUTTERWAVE_BASE_URL}/charges?type=bank_transfer",
                json=payload,
                headers=headers,
            )

        data = response.json()

        if response.status_code != 200 or data.get("status") != "success":
            logger.error(
                "virtual_account_generation_failed",
                tx_ref=tx_ref,
                status_code=response.status_code,
                response=data,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to generate virtual account. Please try again.",
            )

        return data

    except HTTPException:
        raise  

    except httpx.TimeoutException:
        logger.error("virtual_account_timeout", tx_ref=tx_ref)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Bank transfer service timed out. Please try again.",
        )

    except httpx.RequestError as e:
        logger.error("virtual_account_request_error", tx_ref=tx_ref, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach payment provider. Please try again.",
        )

