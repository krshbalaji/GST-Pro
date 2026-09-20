import os

from .demo import (
    DemoCompanyRepository,
    DemoMasterRepository,
    DemoInvoiceRepository,
    DemoApprovalRepository,
    DemoPurchaseRepository,
    DemoReconciliationRepository,
    DemoAuditRepository,
)
from .postgres import (
    PostgresCompanyRepository,
    PostgresMasterRepository,
    PostgresInvoiceRepository,
    PostgresApprovalRepository,
    PostgresPurchaseRepository,
    PostgresReconciliationRepository,
    PostgresAuditRepository,
    PostgresReturnRepository,
)


def build_demo_repositories(state):
    return {
        'companies': DemoCompanyRepository(state['companies']),
        'masters': DemoMasterRepository(state['masters']),
        'invoices': DemoInvoiceRepository(state['invoices']),
        'approvals': DemoApprovalRepository(state['approvals']),
        'purchases': DemoPurchaseRepository(state['purchases']),
        'reconciliation': DemoReconciliationRepository(state['purchases_2b']),
        'audit': DemoAuditRepository(state['audit']),
        'returns': None,
    }


def build_repositories(state=None):
    mode = os.getenv('GSTPRO_MODE', 'demo').lower()
    if mode == 'demo':
        if state is None:
            raise ValueError('Demo repository state is required')
        return build_demo_repositories(state)
    if mode not in {'production', 'prod'}:
        raise RuntimeError(f'Unsupported GSTPRO_MODE: {mode}')
    from ..storage import store
    if not store.enabled:
        raise RuntimeError('DATABASE_URL is required in production mode')
    store.init()
    return {
        'companies': PostgresCompanyRepository(store),
        'masters': PostgresMasterRepository(store),
        'invoices': PostgresInvoiceRepository(store),
        'approvals': PostgresApprovalRepository(store),
        'purchases': PostgresPurchaseRepository(store),
        'reconciliation': PostgresReconciliationRepository(store),
        'audit': PostgresAuditRepository(store),
        'returns': PostgresReturnRepository(store),
    }
