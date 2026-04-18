from datetime import datetime

from pydantic import BaseModel


class CreateBenficiary(BaseModel):
    account_bank: str
    account_number: str
    beneficiary_name: str
    currency: str = "NGN"
    bank_name: str


class BeneficiaryData(BaseModel):
    id: int
    account_number: str
    bank_code: str
    full_name: str
    created_at: datetime
    bank_name: str


class BeneficiaryPageInfo(BaseModel):
    total: int
    current_page: int
    total_pages: int


class BeneficiaryMeta(BaseModel):
    page_info: BeneficiaryPageInfo


class CreateBeneficiaryResponse(BaseModel):
    status: str
    message: str
    data: BeneficiaryData


class ListBeneficiary(CreateBeneficiaryResponse):
    status: str
    message: str
    data: list[BeneficiaryData]
    meta: BeneficiaryMeta


class FetchBeneficiary(CreateBeneficiaryResponse): ...


class DeleteBeneficiaryResponse(BaseModel):
    status: str
    message: str
    data: str



from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PayoutCreate(BaseModel):
    amount: str
    currency: str
    beneficiary:str # Beneficiary ID
    reference: str
    debit_currency: str
    callback_url: str | None = None
    narration: str | None = None


class PayoutData(BaseModel):
   id: str
   account_number: str
   bank_code: str
   full_name: str
   created_at: datetime
   currency:str
   debit_currency:str
   amount: Decimal
   fee: Decimal
   status: str
   reference:str
   meta: str | None = None
   narration:str
   complete_message: str
   requires_approval: int
   is_approved: int
   bank_name:str

class PayoutResponse(BaseModel):
    status: str
    message: str
    data: PayoutData