from app.domain.invoice import InvoiceRules
from app.domain.party import Party
from app.domain.auth import TenantAuthorization, UserContext
from app.domain.returns import ReturnsService
from app.services import authorization_service, invoice_service, compliance_service
from app.repositories.demo import DemoInvoiceRepository


def test_domain_layers_are_importable_and_framework_free():
    party = Party(company_id='demo-company', name='Example')
    assert party.company_id == 'demo-company'
    assert InvoiceRules.is_composition_taxed_invoice('TAX_INVOICE', 'COMPOSITION') is True
    assert ReturnsService.filing_period('2026-09') == '202609'


def test_demo_repository_is_replaceable_contract():
    rows = {}
    repo = DemoInvoiceRepository(rows)
    row = {'id': 'I1', 'request': {'company_id': 'demo-company', 'invoice_date': '2026-09-01'}}
    assert repo.create(row) == row
    assert list(repo.list_by_company('demo-company', '2026-09')) == [row]


def test_tenant_authorization_boundary():
    auth = TenantAuthorization()
    ctx = UserContext(user_id='u1', company_id='c1', role='OWNER')
    auth.require_company(ctx, 'c1')
    try:
        auth.require_company(ctx, 'c2')
        assert False, 'cross-company access should fail'
    except PermissionError:
        pass


def test_service_facade_exposes_domain_services():
    assert authorization_service is not None
    assert invoice_service is not None
    assert compliance_service is not None
