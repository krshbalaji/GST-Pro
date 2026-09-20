from __future__ import annotations
from collections.abc import MutableMapping
from uuid import UUID

def _uuid(value):
    return value if isinstance(value, UUID) else UUID(str(value))

class ProductionMapping(MutableMapping):
    def __init__(self, repo, kind, all_rows):
        self.repo,self.kind,self._all_rows=repo,kind,all_rows
    def __getitem__(self,key):
        row=self.get(key)
        if row is None: raise KeyError(key)
        return row
    def get(self,key,default=None):
        try:
            if self.kind=="companies": row=self.repo.get(key)
            elif self.kind in {"gstins","customers","vendors","products","users"}: row=self.repo.get(self.kind,key)
            elif self.kind=="invoices": row=self.repo.get(key)
            elif self.kind=="approvals": row=self.repo.get(key)
            else: row=next((r for r in self._all_rows() if str(r.get("id"))==str(key)),None)
        except (ValueError,TypeError): row=None
        return default if row is None else row
    def __setitem__(self,key,row):
        row=dict(row); row["id"]=str(row.get("id") or key)
        if self.kind=="companies": return self.repo.save(row) if self.repo.get(row["id"]) else self.repo.create(row)
        if self.kind in {"gstins","customers","vendors","products","users"}: return self.repo.save(self.kind,row) if self.repo.get(self.kind,row["id"]) else self.repo.create(self.kind,row)
        if self.kind=="invoices": return self.repo.save(row) if self.repo.get(row["id"]) else self.repo.create(row)
        if self.kind=="approvals": return self.repo.save(row)
        if self.kind=="purchases": return self.repo.save(row) if self.get(row["id"]) else self.repo.create(row)
        if self.kind=="purchases_2b": return self.repo.upsert_2b(row)
        if self.kind=="audit": return self.repo.append(row)
        if self.kind=="returns": return self.repo.save(row)
        raise KeyError(self.kind)
    def __delitem__(self,key):
        if self.kind=="invoices": table,ident="invoices",_uuid(key)
        elif self.kind in {"gstins","customers","vendors","products","users"}: table,ident=self.repo.TABLES[self.kind],_uuid(key)
        elif self.kind in {"purchases","purchases_2b"}: table,ident="gstr2b_entries",_uuid(key)
        else: raise KeyError(self.kind)
        if self.repo._one(f"DELETE FROM {table} WHERE id=%s RETURNING id",(ident,)) is None: raise KeyError(key)
    def __iter__(self): return (str(r["id"]) for r in self.values())
    def __len__(self): return len(self.values())
    def values(self): return list(self._all_rows())
    def items(self): return [(str(r["id"]),r) for r in self.values()]
    def update(self,other=None,**kwargs):
        data={}; data.update(other or {}); data.update(kwargs)
        for k,v in data.items(): self[k]=v

class AuditMapping(ProductionMapping):
    def __getitem__(self,key): return self.values()[key] if isinstance(key,(int,slice)) else super().__getitem__(key)
    def append(self,row): return self.repo.append(row)

class ProductionState:
    def __init__(self,repos):
        company=repos["companies"]; master=repos["masters"]; invoice=repos["invoices"]; purchase=repos["purchases"]; recon=repos["reconciliation"]; audit=repos["audit"]; approval=repos["approvals"]; ret=repos["returns"]
        self.companies=ProductionMapping(company,"companies",lambda: company._all("SELECT * FROM companies ORDER BY id"))
        self.gstins=ProductionMapping(master,"gstins",lambda: master._all("SELECT * FROM gstins ORDER BY id"))
        self.customers=ProductionMapping(master,"customers",lambda: master._all("SELECT * FROM customers ORDER BY id"))
        self.vendors=ProductionMapping(master,"vendors",lambda: master._all("SELECT * FROM vendors ORDER BY id"))
        self.products=ProductionMapping(master,"products",lambda: master._all("SELECT * FROM products ORDER BY id"))
        self.users=ProductionMapping(master,"users",lambda: master._all("SELECT * FROM users ORDER BY id"))
        self.invoices=ProductionMapping(invoice,"invoices",lambda: invoice.list_all())
        self.purchases=ProductionMapping(purchase,"purchases",lambda: purchase._all("SELECT * FROM gstr2b_entries ORDER BY id"))
        self.purchases_2b=ProductionMapping(recon,"purchases_2b",lambda: recon._all("SELECT * FROM gstr2b_entries ORDER BY id"))
        self.audit=AuditMapping(audit,"audit",lambda: audit._all("SELECT * FROM audit_logs ORDER BY created_at,id"))
        self.approvals=ProductionMapping(approval,"approvals",lambda: approval._all("SELECT * FROM invoice_approvals ORDER BY created_at"))
        self.returns=ProductionMapping(ret,"returns",lambda: ret._all("SELECT * FROM return_periods ORDER BY period,return_type"))
