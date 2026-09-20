from ..domain.services import AuthorizationService, InvoiceDomainService, ComplianceService, TenantContext

authorization_service = AuthorizationService()
invoice_service = InvoiceDomainService()
compliance_service = ComplianceService()

__all__ = [
    "authorization_service",
    "invoice_service",
    "compliance_service",
    "TenantContext",
]
