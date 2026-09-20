from dataclasses import dataclass
from typing import Iterable, Optional

from ..gst import calculate_invoice, hsn_min_digits, Scheme

@dataclass
class TenantContext:
    user_id: str
    company_id: str
    role: str

class AuthorizationService:
    def require_company(self, context: TenantContext, company_id: str) -> None:
        if context.company_id != company_id:
            raise PermissionError("Cross-company access denied")

    def can(self, context: TenantContext, permission: str, roles: dict[str, set[str]]) -> bool:
        return permission in roles.get(context.role, set())

class InvoiceDomainService:
    def calculate(self, lines: list[dict], scheme: Scheme, supplier_state: str, place_of_supply: str) -> dict:
        return calculate_invoice(lines, scheme, supplier_state, place_of_supply)

    def validate_hsn(self, hsn_sac: str, aato: float) -> None:
        digits = ''.join(c for c in hsn_sac if c.isdigit())
        if len(digits) > 8:
            raise ValueError("HSN/SAC cannot exceed 8 digits.")
        if digits and len(digits) < hsn_min_digits(aato):
            raise ValueError(f"HSN/SAC requires at least {hsn_min_digits(aato)} digits for this AATO.")

class ComplianceService:
    def ensure_period_open(self, return_rows: Iterable[dict], gstin_id: str, invoice_date: str) -> None:
        period = invoice_date[:7]
        for row in return_rows:
            if row.get("gstin_id") == gstin_id and row.get("period") == period and row.get("status") == "LOCKED":
                raise ValueError(f"Return period {period} is locked for {row.get('return_type')}; invoice changes are blocked.")

    def maker_checker_allows(self, approval: Optional[dict], actor_user_id: str) -> None:
        if not approval or approval.get("status") != "PENDING":
            raise ValueError("Invoice is not pending approval")
        if approval.get("submitted_by") == actor_user_id:
            raise ValueError("Maker-checker control: the submitting user cannot approve the same invoice.")
