from typing import Optional

class DemoCompanyRepository:
    def __init__(self, companies):
        self.companies = companies

    def list_by_company(self, company_id: str):
        return [x for x in self.companies.values() if x.get('id') == company_id]

class DemoMasterRepository:
    def __init__(self, masters: dict[str, dict]):
        self.masters = masters

    def list_by_company(self, kind: str, company_id: str):
        return [x for x in self.masters.get(kind, {}).values() if x.get('company_id') == company_id]

class DemoInvoiceRepository:
    def __init__(self, invoices): self.invoices = invoices
    def create(self, row: dict): self.invoices[row['id']] = row; return row
    def get(self, invoice_id: str) -> Optional[dict]: return self.invoices.get(invoice_id)
    def list_by_company(self, company_id: str, period: Optional[str] = None):
        rows = [x for x in self.invoices.values() if x.get('request', {}).get('company_id') == company_id]
        if period: rows = [x for x in rows if x.get('request', {}).get('invoice_date', '')[:7] == period]
        return rows
    def save(self, row: dict): self.invoices[row['id']] = row; return row

class DemoApprovalRepository:
    def __init__(self, approvals): self.approvals = approvals
    def get(self, invoice_id: str): return self.approvals.get(invoice_id)
    def save(self, approval: dict): self.approvals[approval['invoice_id']] = approval; return approval
    def list_by_company(self, company_id: str, invoice_lookup):
        return [x for x in self.approvals.values() if invoice_lookup(x['invoice_id']) and invoice_lookup(x['invoice_id']).get('request', {}).get('company_id') == company_id]

class DemoPurchaseRepository:
    def __init__(self, purchases): self.purchases = purchases
    def list_by_company(self, company_id: str, period: Optional[str] = None):
        rows = [x for x in self.purchases.values() if x.get('company_id') == company_id]
        if period: rows = [x for x in rows if x.get('invoice_date', '')[:7] == period]
        return rows
    def create(self, row: dict): self.purchases[row['id']] = row; return row

class DemoReconciliationRepository:
    def __init__(self, rows): self.rows = rows
    def list_2b(self, company_id: str, period: str):
        return [x for x in self.rows.values() if x.get('company_id') == company_id and x.get('invoice_date', '')[:7] == period]
    def upsert_2b(self, row: dict): self.rows[row['id']] = row; return row

class DemoAuditRepository:
    def __init__(self, audit_rows): self.audit_rows = audit_rows
    def append(self, row: dict): self.audit_rows.append(row); return row
    def list_by_company(self, company_id: str): return [x for x in self.audit_rows if x.get('company_id') == company_id]
