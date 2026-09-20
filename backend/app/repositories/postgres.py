from __future__ import annotations

from datetime import date
from typing import Optional

from psycopg.rows import dict_row

class _Base:
    def __init__(self, store): self.store = store

class PostgresCompanyRepository(_Base):
    def list_by_company(self, company_id: str):
        with self.store.connect() as c:
            return c.execute("SELECT * FROM companies WHERE id=%s::uuid", (company_id,)).fetchall()

class PostgresMasterRepository(_Base):
    TABLES = {"gstins":"gstins","customers":"customers","vendors":"vendors","products":"products","users":"users"}
    def list_by_company(self, kind: str, company_id: str):
        table=self.TABLES[kind]
        with self.store.connect() as c:
            return c.execute(f"SELECT * FROM {table} WHERE company_id=%s::uuid", (company_id,)).fetchall()

class PostgresInvoiceRepository(_Base):
    def create(self, row: dict): return row
    def get(self, invoice_id: str): 
        with self.store.connect() as c:
            return c.execute("SELECT * FROM invoices WHERE id=%s::uuid", (invoice_id,)).fetchone()
    def list_by_company(self, company_id: str, period: Optional[str]=None):
        sql="SELECT i.* FROM invoices i JOIN gstins g ON g.id=i.gstin_id WHERE g.company_id=%s::uuid"
        params=[company_id]
        if period: sql += " AND to_char(i.invoice_date,'YYYY-MM')=%s"; params.append(period)
        with self.store.connect() as c: return c.execute(sql,params).fetchall()
    def save(self,row:dict): return row

class PostgresApprovalRepository(_Base):
    def get(self, invoice_id:str):
        with self.store.connect() as c: return c.execute("SELECT * FROM invoice_approvals WHERE invoice_id=%s::uuid",(invoice_id,)).fetchone()
    def save(self,approval:dict): return approval
    def list_by_company(self,company_id:str,invoice_lookup):
        with self.store.connect() as c:
            return c.execute("SELECT a.* FROM invoice_approvals a JOIN invoices i ON i.id=a.invoice_id JOIN gstins g ON g.id=i.gstin_id WHERE g.company_id=%s::uuid",(company_id,)).fetchall()

class PostgresPurchaseRepository(_Base):
    def list_by_company(self,company_id:str,period:Optional[str]=None):
        with self.store.connect() as c:
            sql="SELECT p.* FROM gstr2b_entries p JOIN gstins g ON g.id=p.gstin_id WHERE g.company_id=%s::uuid"
            params=[company_id]
            if period: sql+=" AND to_char(p.invoice_date,'YYYY-MM')=%s"; params.append(period)
            return c.execute(sql,params).fetchall()
    def create(self,row:dict): return row

class PostgresReconciliationRepository(_Base):
    def list_2b(self,company_id:str,period:str):
        with self.store.connect() as c:
            return c.execute("SELECT e.* FROM gstr2b_entries e JOIN gstins g ON g.id=e.gstin_id WHERE g.company_id=%s::uuid AND to_char(e.invoice_date,'YYYY-MM')=%s",(company_id,period)).fetchall()
    def upsert_2b(self,row:dict): return row

class PostgresAuditRepository(_Base):
    def append(self,row:dict): return row
    def list_by_company(self,company_id:str):
        with self.store.connect() as c: return c.execute("SELECT * FROM audit_logs WHERE company_id=%s::uuid ORDER BY created_at",(company_id,)).fetchall()
