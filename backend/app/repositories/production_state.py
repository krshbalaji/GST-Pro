from __future__ import annotations

from collections.abc import MutableMapping
from uuid import UUID, uuid4

from .postgres import _uuid


class _Mapping(MutableMapping):
    def __init__(self, repo, kind, *, company_getter=None):
        self.repo = repo
        self.kind = kind
        self.company_getter = company_getter

    def _company_id(self, row):
        if self.company_getter:
            return self.company_getter(row)
        return row.get("company_id")

    def __getitem__(self, key):
        row = self.get(key)
        if row is None:
            raise KeyError(key)
        return row

    def __setitem__(self, key, row):
        row = dict(row)
        row["id"] = str(row.get("id") or key)
        if self.kind == "companies":
            result = self.repo.create(row) if self.repo.get(row["id"]) is None else self.repo.save(row)
        elif self.kind in {"gstins","customers","vendors","products","users"}:
            existing = self.repo.get(self.kind, row["id"])
            result = self.repo.create(self.kind, row) if existing is None else self.repo.save(self.kind, row)
        elif self.kind == "invoices":
            result = self.repo.create(row) if self.repo.get(row["id"]) is None else self.repo.save(row)
        elif self.kind == "approvals":
            result = self.repo.save(row)
        elif self.kind == "purchases":
            existing = self.repo._one("SELECT id FROM gstr2b_entries WHERE id=%s", (_uuid(row["id"]),))
            result = self.repo.create(row) if existing is None else self.repo.save(row)
        elif self.kind == "purchases_2b":
            result = self.repo.upsert_2b(row)
        elif self.kind == "audit":
            result = self.repo.append(row)
        elif self.kind == "returns":
            result = self.repo.save(row)
        else:
            raise KeyError(self.kind)
        return result

    def __delitem__(self, key):
        if self.kind in {"customers","vendors","products","gstins","users"}:
            table=self.repo.TABLES[self.kind]
            self.repo._one(f"DELETE FROM {table} WHERE id=%s RETURNING id", (_uuid(key),))
        elif self.kind == "invoices":
            self.repo._one("DELETE FROM invoices WHERE id=%s RETURNING id", (_uuid(key),))
        elif self.kind == "purchases_2b":
            self.repo._one("DELETE FROM gstr2b_entries WHERE id=%s RETURNING id", (_uuid(key),))
        else:
            raise KeyError(f"Deletion unsupported for {self.kind}")

    def __iter__(self):
        for row in self.values():
            yield str(row["id"])

    def __len__(self):
        return len(self.values())

    def get(self, key, default=None):
        if self.kind == "companies":
            row = self.repo.get(key)
        elif self.kind in {"gstins","customers","vendors","products","users"}:
            row = self.repo.get(self.kind,key)
        elif self.kind == "invoices":
            row = self.repo.get(key)
        elif self.kind == "approvals":
            row = self.repo.get(key)
        elif self.kind == "returns":
            rows = self.repo.list_by_gstin(key) if hasattr(self.repo,"list_by_gstin") else []
            row = rows[0] if rows else None
        elif self.kind in {"purchases","purchases_2b"}:
            row = next((x for x in self.values() if str(x.get("id")) == str(key)), None)
        elif self.kind == "audit":
            row = next((x for x in self.values() if str(x.get("id")) == str(key)), None)
        else:
            row = None
        return default if row is None else row

    def values(self):
        if self.kind == "companies":
            # Production callers only need the authenticated company. This returns all companies only for administrative diagnostics.
            return self.repo._all("SELECT * FROM companies ORDER BY id")
        if self.kind in {"gstins","customers","vendors","products","users"}:
            return self.repo._all(f"SELECT * FROM {self.repo.TABLES[self.kind]} ORDER BY id")
        if self.kind == "invoices":
            return self.repo._all("SELECT id FROM invoices ORDER BY id") and [self.repo.get(str(x["id"])) for x in self.repo._all("SELECT id FROM invoices ORDER BY id")]
        if self.kind == "approvals":
            return self.repo._all("SELECT * FROM invoice_approvals ORDER BY created_at")
        if self.kind == "purchases":
            return self.repo._all("SELECT * FROM gstr2b_entries ORDER BY id")
        if self.kind == "purchases_2b":
            return self.repo._all("SELECT * FROM gstr2b_entries ORDER BY id")
        if self.kind == "audit":
            return self.repo._all("SELECT * FROM audit_logs ORDER BY created_at,id")
        if self.kind == "returns":
            return self.repo._all("SELECT * FROM return_periods ORDER BY period,return_type")
        return []

    def items(self):
        return [(str(x["id"]),x) for x in self.values()]

    def __contains__(self,key):
        return self.get(key) is not None

    def update(self, other=None, **kwargs):
        data={}
        if other is not None:
            data.update(other)
        data.update(kwargs)
        for k,v in data.items():
            self[k]=v


class AuditMapping(_Mapping):
    def append(self, row):
        self.repo.append(row)
        return row

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.values()[key]
        if isinstance(key, int):
            return self.values()[key]
        return super().__getitem__(key)


class ProductionState:
    def __init__(self, repositories):
        self.repos=repositories
        self.companies=_Mapping(repositories["companies"],"companies")
        master=repositories["masters"]
        self.gstins=_Mapping(master,"gstins")
        self.customers=_Mapping(master,"customers")
        self.vendors=_Mapping(master,"vendors")
        self.products=_Mapping(master,"products")
        self.users=_Mapping(master,"users")
        self.invoices=_Mapping(repositories["invoices"],"invoices")
        self.purchases=_Mapping(repositories["purchases"],"purchases")
        self.purchases_2b=_Mapping(repositories["reconciliation"],"purchases_2b")
        self.audit=AuditMapping(repositories["audit"],"audit")
        self.approvals=_Mapping(repositories["approvals"],"approvals")
        self.returns=_Mapping(repositories["reconciliation"],"returns")
