from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from supabase import AsyncClient

from app.schemas import beneficiary_schema
from app.schemas.beneficiary_schema import PayoutCreate
from app.services.vendors.payout_service import BeneficiaryService, TransferService
from app.dependencies.auth import get_current_profile, get_customer_contact_info
from app.database.supabase import get_supabase_client, get_supabase_admin_client
from app.config.logging import logger
from app.config.config import settings
from app.dependencies.auth import require_admin

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/beneficiaries", tags=["Beneficiaries"])

payout_router = APIRouter(prefix="/api/v1/payouts", tags=["Payouts"])

# ---------------------------------------------------------------------------
# Service instances  (base_url is the root v3 URL – path segments are built
# inside each service method, so do NOT append them here)
# ---------------------------------------------------------------------------

service = BeneficiaryService(
    base_url=settings.FLUTTERWAVE_BASE_URL,
    secret_key=settings.FLW_SECRET_KEY,
)

payout_service = TransferService(
    base_url=settings.FLUTTERWAVE_BASE_URL,
    secret_key=settings.FLW_SECRET_KEY,
)


# ===========================================================================
# Beneficiary routes
# ===========================================================================


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_beneficiary(
    data: beneficiary_schema.CreateBenficiary,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
) -> beneficiary_schema.CreateBeneficiaryResponse:
    """Create a new transfer beneficiary on Flutterwave and persist it locally."""
    response = await service.create_beneficiary(payload=data.model_dump())
    print("=" * 100)
    logger.info(f"Beneficiary created on Flutterwave with response: {response}")
    print("=" * 100)
    beneficiary_data = response.get("data", {})
    beneficiary_id = beneficiary_data.get("id")

    try:
        await (
            supabase.table("beneficiaries")
            .insert(
                {
                    "beneficiary_id": beneficiary_id,
                    "account_number": beneficiary_data.get("account_number"),
                    "bank_code": beneficiary_data.get("bank_code"),
                    "full_name": beneficiary_data.get("full_name"),
                    "created_at": beneficiary_data.get("created_at"),
                    "bank_name": beneficiary_data.get("bank_name"),
                }
            )
            .execute()
        )
    except Exception as e:
        logger.error(f"Error persisting beneficiary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Beneficiary created on Flutterwave but failed to save locally.",
        )

    return response


@router.get("", status_code=status.HTTP_200_OK)
async def list_beneficiaries(
    page: int = 1,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
    current_user: dict = Depends(require_admin),
) -> beneficiary_schema.ListBeneficiary:
    """Return a paginated list of all beneficiaries."""
    return await service.list_beneficiaries(page=page)


@router.get("/{beneficiary_id}", status_code=status.HTTP_200_OK)
async def fetch_beneficiary(
    beneficiary_id: int,
    current_user: dict = Depends(require_admin),
) -> beneficiary_schema.FetchBeneficiary:
    """Fetch a single beneficiary by ID."""
    return await service.fetch_beneficiary(
        customer_contact_info={"beneficiary_id": beneficiary_id}
    )


@router.delete("/{beneficiary_id}", status_code=status.HTTP_200_OK)
async def delete_beneficiary(
    beneficiary_id: int,
    current_user: dict = Depends(require_admin),
    supabase: AsyncClient = Depends(get_supabase_client),
) -> beneficiary_schema.DeleteBeneficiaryResponse:
    """Delete a beneficiary by ID."""
    response = await service.delete_beneficiary(beneficiary_id=beneficiary_id)

    try:
        await (
            supabase.table("beneficiaries")
            .delete()
            .eq("beneficiary_id", beneficiary_id)
            .execute()
        )
    except Exception as e:
        logger.error(f"Error deleting beneficiary from db: {e}")

    return response


@router.put("/{beneficiary_id}", status_code=status.HTTP_200_OK)
async def update_beneficiary(
    beneficiary_id: int,
    data: beneficiary_schema.CreateBenficiary,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
) -> beneficiary_schema.CreateBeneficiaryResponse:
    """Update a beneficiary by deleting the old one and creating a new one."""
    # 1. Delete existing beneficiary from flutterwave
    try:
        await service.delete_beneficiary(beneficiary_id=beneficiary_id)
    except Exception as e:
        logger.error(f"Error deleting existing beneficiary on flutterwave: {e}")
        # Assuming we might want to continue to create a new one even if delete fails
        # but if it was not found on Flutterwave, the delete endpoint might return error

    # Delete from local supabase
    try:
        await (
            supabase.table("beneficiaries")
            .delete()
            .eq("beneficiary_id", beneficiary_id)
            .execute()
        )
    except Exception as e:
        logger.error(f"Error deleting existing beneficiary locally: {e}")

    # 2. Create new beneficiary on flutterwave
    response = await service.create_beneficiary(payload=data.model_dump())
    beneficiary_data = response.get("data", {})
    new_beneficiary_id = beneficiary_data.get("id")

    # 3. Save new beneficiary locally
    try:
        await (
            supabase.table("beneficiaries")
            .insert(
                {
                    "beneficiary_id": new_beneficiary_id,
                    "account_number": beneficiary_data.get("account_number"),
                    "bank_code": beneficiary_data.get("bank_code"),
                    "full_name": beneficiary_data.get("full_name"),
                    "created_at": beneficiary_data.get("created_at"),
                    "bank_name": beneficiary_data.get("bank_name"),
                }
            )
            .execute()
        )
    except Exception as e:
        logger.error(f"Error persisting new beneficiary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Beneficiary updated on Flutterwave but failed to save locally.",
        )

    return response


# ===========================================================================
# Payout / Transfer routes
# ===========================================================================


@payout_router.post(
    "/{order_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a payout for a vendor/dispatch order",
)
async def create_vendor_payout(
    order_id: str,
    supabase: AsyncClient = Depends(get_supabase_client),
    customer_contact_info: dict = Depends(get_customer_contact_info),
):
    """Create and execute a transfer for the given order, paying out to the vendor."""
    return await payout_service.create_transfer(
        order_id=order_id,
        payout_to="VENDOR",
        supabase=supabase,
    )


@payout_router.post(
    "/{transfer_id}/retry",
    status_code=status.HTTP_200_OK,
    summary="Retry a failed transfer",
)
async def retry_transfer(
    transfer_id: int,
    current_user: dict = Depends(require_admin),
):
    """Retry a previously failed Flutterwave transfer."""
    return await payout_service.retry_transfer(transfer_id=transfer_id)


@payout_router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List all transfers",
)
async def get_transfers(
    page: int | None = None,
    transfer_status: str | None = None,
    account_id: str | None = None,
    current_user: dict = Depends(require_admin),
):
    """Fetch all transfers with optional pagination and status filters."""
    return await payout_service.get_transfers(
        page=page,
        status_filter=transfer_status,
        account_id=account_id,
    )


@payout_router.get(
    "/{transfer_id}",
    status_code=status.HTTP_200_OK,
    summary="Get a single transfer",
)
async def get_transfer(
    transfer_id: int,
    current_user: dict = Depends(require_admin),
):
    """Fetch details of a single transfer by its Flutterwave ID."""
    return await payout_service.get_transfer(transfer_id=transfer_id)


@payout_router.get(
    "/{transfer_id}/retries",
    status_code=status.HTTP_200_OK,
    summary="Get retry attempts for a transfer",
)
async def get_transfer_retry(
    transfer_id: int,
    current_user: dict = Depends(require_admin),
):
    """Fetch all retry attempts that have been made for a given transfer."""
    return await payout_service.get_transfer_retry(transfer_id=transfer_id)
