import os
os.environ.setdefault("GSTPRO_MODE","demo")
from uuid import uuid4

from app.repositories.demo import DemoInvoiceRepository
from app.repositories.factory import build_repositories


def test_demo_factory_remains_explicit():
    state={k:{} for k in ("companies","gstins","customers","vendors","products","users","invoices","purchases","purchases_2b","approvals")}
    state["audit"]=[]
    state["returns"]={}
    repos=build_repositories(state)
    assert repos["invoices"].__class__.__name__=="DemoInvoiceRepository"


def test_production_factory_fails_without_database_url(monkeypatch):
    monkeypatch.setenv("GSTPRO_MODE","production")
    monkeypatch.delenv("DATABASE_URL",raising=False)
    try:
        build_repositories()
        assert False, "production mode must require DATABASE_URL"
    except RuntimeError as exc:
        assert "DATABASE_URL" in str(exc)


def test_demo_invoice_contract_is_unchanged():
    rows={}
    repo=DemoInvoiceRepository(rows)
    invoice={"id":"demo-invoice","request":{"company_id":"demo-company","invoice_date":"2026-09-01"}}
    assert repo.create(invoice)==invoice
    assert repo.get("demo-invoice")==invoice
    assert list(repo.list_by_company("demo-company","2026-09"))==[invoice]
