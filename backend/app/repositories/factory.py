from .demo import DemoCompanyRepository, DemoMasterRepository, DemoInvoiceRepository, DemoApprovalRepository, DemoPurchaseRepository, DemoReconciliationRepository, DemoAuditRepository


def build_demo_repositories(state):
    return {
        'companies': DemoCompanyRepository(state['companies']),
        'masters': DemoMasterRepository(state['masters']),
        'invoices': DemoInvoiceRepository(state['invoices']),
        'approvals': DemoApprovalRepository(state['approvals']),
        'purchases': DemoPurchaseRepository(state['purchases']),
        'reconciliation': DemoReconciliationRepository(state['purchases_2b']),
        'audit': DemoAuditRepository(state['audit']),
    }
