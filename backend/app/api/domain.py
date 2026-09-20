from fastapi import APIRouter, Depends, HTTPException

from ..security import ROLES
from ..services import authorization_service, invoice_service, compliance_service, TenantContext

router = APIRouter(prefix='/api/v2', tags=['domain-services'])

@router.get('/architecture')
def architecture():
    return {
        'domain': ['invoice', 'party', 'auth', 'compliance', 'einvoice', 'returns'],
        'services': ['authorization', 'invoice', 'compliance'],
        'repositories': ['company', 'master', 'invoice', 'approval', 'purchase', 'reconciliation', 'audit'],
        'repository_mode': 'demo',
    }

@router.post('/invoice/calculate')
def calculate_invoice_v2(payload: dict):
    scheme = payload.get('scheme', 'REGULAR')
    from ..gst import Scheme
    try:
        scheme_value = Scheme(scheme)
    except ValueError:
        raise HTTPException(422, 'Invalid scheme')
    return invoice_service.calculate(
        payload.get('lines', []),
        scheme_value,
        payload.get('supplier_state_code', ''),
        payload.get('place_of_supply', ''),
    )
