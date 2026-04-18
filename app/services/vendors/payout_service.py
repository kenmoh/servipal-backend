from typing import Any, Literal
from decimal import Decimal
import httpx
from fastapi import HTTPException, status

from supabase import AsyncClient

# from app.common.order import get_delivery_order_by_id_for_payout
from app.config.config import settings
from app.schemas.beneficiary_schema import PayoutCreate, PayoutData


async def get_delivery_order_by_id_for_payout(order_id: str, payout_to: Literal['CUSTOMER', 'VENDOR'], supabase: AsyncClient):
    resp = await supabase.rpc('unified_order_funds', {
        'p_order_id': order_id,
        'p_payout_to': payout_to

    }).execute()

    return resp.data[0]

TRANSFER_URL = "https://api.flutterwave.com/v3/transfers"


# Beneficary
class BeneficiaryService:
    def __init__(
        self, *, base_url: str, secret_key: str, timeout_in_sec: float = 6.0
    ) -> None:
        self._base_url = base_url or settings.FLUTTERWAVE_BASE_URL
        self._secret_key = secret_key or settings.FLW_SECRET_KEY
        self._timeout_in_sec = timeout_in_sec

        if not self._secret_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Flutterwave secret key not configured (FLW_SECRET_KEY).",
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    def _beneficiary_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    async def create_beneficiary(self, payload) -> dict[str, Any]:
        body = self._beneficiary_data(payload=payload)
        header = self._headers()
        url = f"{self._base_url}/beneficiaries"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=self._headers(), json=body)
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Flutterwave beneficiary creation failed",
                    "response": data,
                },
            )

        return data

    async def list_beneficiaries(self, page: int = None) -> dict[str, Any]:
        url = f"{self._base_url}/beneficiaries?page={page}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers())
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Error fetching beneficiaries",
                    "response": data,
                },
            )

        return data

    async def fetch_beneficiary(self, customer_contact_info: dict) -> dict[str, Any]:

        beneficiary_id = customer_contact_info["beneficiary_id"]
        url = f"{self._base_url}/beneficiaries/{beneficiary_id}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers())
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Failed to fetch beneficiary",
                    "response": data,
                },
            )

        return data

    async def delete_beneficiary(self, beneficiary_id: int) -> dict[str, Any]:
        url = f"{self._base_url}/beneficiaries/{beneficiary_id}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_in_sec) as client:
                resp = await client.delete(url, headers=self._headers())
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Failed to delete beneficiary",
                    "response": data,
                },
            )

        return data




class TransferService:
    def __init__(
            self, *, base_url: str, secret_key: str, timeout_in_sec: float = 6.0
    ) -> None:
        self._base_url = base_url or settings.FLUTTERWAVE_BASE_URL
        self._secret_key = secret_key or settings.FLW_SECRET_KEY
        self._timeout_in_sec = timeout_in_sec
        self.beneficiary = BeneficiaryService(
            base_url=self._base_url, secret_key=self._secret_key
        )

        if not self._secret_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Flutterwave secret key not configured (FLW_SECRET_KEY).",
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    def _transfer_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    # Get transfer fee
    async def get_bank_transfer_fee(self, amount: Decimal):
        url = f'{self._base_url}/transfers/fee?amount={amount}&currency=NGN&type=account'
        try:
            async with httpx.AsyncClient(timeout=self._timeout_in_sec) as client:
                resp = await client.get(url, headers=self._headers())
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Failed to get transfer",
                    "response": data,
                },
            )
        transfer_fer = data.get('data')[0].get('fee')
        return transfer_fer

    # Create transafer
    async def create_transfer(self, order_id: str, payout_to: str, supabase: AsyncClient) -> dict[str, Any]:

        vendor_amount = Decimal('0')
        order = await get_delivery_order_by_id_for_payout(order_id=order_id, payout_to=payout_to, supabase=supabase)
        beneficiary = order['beneficiary_id']
        tx_ref = order['tx_ref']
        amount_due_vendor = order['amount_due_vendor'] or order['amount_due_dispatch'] or order['vendor_payout']
        transfer_fee = await self.get_bank_transfer_fee(f'{amount_due_vendor}')

        vendor_amount = Decimal(amount_due_vendor) - Decimal(transfer_fee)

        service = tx_ref.split('_')[0]

        transfer_data = PayoutCreate(
            amount=f'{vendor_amount}',
            currency='NGN',
            beneficiary=beneficiary,
            reference=tx_ref,
            debit_currency='NGN',
            narration=f'Form for {service} service.'
        )

        body = self._transfer_payload(payload=transfer_data.model_dump())
        url = f"{self._base_url}/transfers"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_in_sec) as client:
                resp = await client.post(url, headers=self._headers(), json=body)
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Flutterwave beneficiary creation failed",
                    "response": data,
                },
            )

        response_data = data['data']
        payout_response_data = PayoutData(
                id=response_data['id'],
                account_number=response_data['account_number'],
                bank_code=response_data['bank_code'],
                full_name=response_data['full_name'],
                created_at=response_data['created_at'],
                currency=response_data['currency'],
                debit_currency=response_data['debit_currency'],
                amount=response_data['amount'],
                fee=response_data['fee'],
                status=response_data['status'],
                reference=response_data['reference'],
                meta=response_data['meta'],
                narration=response_data['narrations'],
                complete_message=response_data['complete_message'],
                requires_approval=response_data['requires_approval'],
                is_approved=response_data['is_approved'],
                bank_name=response_data['bank_name']
        )
        await supabase.table('payouts').insert(**payout_response_data.model_dump()).execute()
        return data


    # Retry transfer
    async def retry_transfer(self, transfer_id: int) -> dict[str, Any]:
        """Retry a previously failed transfer.
        POST /transfers/{id}/retries
        """
        url = f"{self._base_url}/transfers/{transfer_id}/retries"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_in_sec) as client:
                resp = await client.post(url, headers=self._headers())
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code not in (200, 201) or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"message": "Failed to retry transfer", "response": data},
            )

        return data

    # Get transfers
    async def get_transfers(
        self,
        page: int | None = None,
        status_filter: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch all transfers, with optional filters.
        GET /transfers?page=&status=&account_id=
        """
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if status_filter is not None:
            params["status"] = status_filter
        if account_id is not None:
            params["account_id"] = account_id

        url = f"{self._base_url}/transfers"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_in_sec) as client:
                resp = await client.get(url, headers=self._headers(), params=params)
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"message": "Failed to fetch transfers", "response": data},
            )

        return data

    # Get transfer
    async def get_transfer(self, transfer_id: int) -> dict[str, Any]:
        """Fetch a single transfer by its ID.
        GET /transfers/{id}
        """
        url = f"{self._base_url}/transfers/{transfer_id}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_in_sec) as client:
                resp = await client.get(url, headers=self._headers())
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"message": f"Failed to fetch transfer {transfer_id}", "response": data},
            )

        return data

    # Get transfer retry
    async def get_transfer_retry(self, transfer_id: int) -> dict[str, Any]:
        """Fetch all retry attempts for a given transfer.
        GET /transfers/{id}/retries
        """
        url = f"{self._base_url}/transfers/{transfer_id}/retries"

        try:
            async with httpx.AsyncClient(timeout=self._timeout_in_sec) as client:
                resp = await client.get(url, headers=self._headers())
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"Failed to fetch retries for transfer {transfer_id}",
                    "response": data,
                },
            )

        return data
