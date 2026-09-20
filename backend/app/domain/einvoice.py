from dataclasses import dataclass

@dataclass(frozen=True)
class EInvoiceRequest:
    invoice_id: str

@dataclass(frozen=True)
class EInvoiceResult:
    status: str
    irn: str

class EInvoiceRules:
    @staticmethod
    def approval_required(status: str) -> bool:
        return status not in {'APPROVED', 'EINVOICE_GENERATED'}
