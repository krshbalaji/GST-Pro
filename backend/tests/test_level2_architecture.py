import os
os.environ.setdefault("GSTPRO_MODE", "demo")
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

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


def test_service_facade_and_router_boundary():
    assert authorization_service is not None
    assert invoice_service is not None
    assert compliance_service is not None
    response = client.get('/api/v2/architecture')
    assert response.status_code == 200
    payload = response.json()
    assert payload['repository_mode'] == 'demo'
    assert 'invoice' in payload['domain']


def test_v2_invoice_calculation_uses_domain_service():
    response = client.post('/api/v2/invoice/calculate', json={
        'scheme': 'REGULAR', 'supplier_state_code': '33', 'place_of_supply': '29',
        'lines': [{'description': 'Test', 'hsn_sac': '620520', 'unit': 'PCS', 'qty': 2, 'rate': 1000, 'gst_rate': 18}]
    })
    assert response.status_code == 200
    assert response.json()['igst'] == 360
