from dataclasses import dataclass

@dataclass(frozen=True)
class ReturnDraft:
    gstin_id: str
    return_type: str
    period: str
    status: str = 'DRAFT'

class ReturnsService:
    @staticmethod
    def period(invoice_date: str) -> str:
        return invoice_date[:7]

    @staticmethod
    def filing_period(period: str) -> str:
        return period.replace('-', '')
