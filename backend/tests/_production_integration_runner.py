import os
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ["GSTPRO_MODE"] = "production"
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://gstpro:gstpro@localhost:5432/gstpro",
)

from fastapi.testclient import TestClient
from app.main import app
from app.production_bootstrap import bootstrap_enabled


client = TestClient(app)


def login(email="admin@gstpro.local", password="admin"):
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def production_headers(email="admin@gstpro.local", password="admin"):
    return {"Authorization": "Bearer " + login(email, password)}


def case_ready():
    response = client.get("/ready")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "production"
    assert payload["database"]["enabled"] is True
    assert payload["database"]["status"] == "ok"


def case_bootstrap():
    original = os.getenv("GSTPRO_BOOTSTRAP")
    try:
        os.environ["GSTPRO_BOOTSTRAP"] = "0"
        assert bootstrap_enabled() is False

        os.environ["GSTPRO_BOOTSTRAP"] = "1"
        assert bootstrap_enabled() is True
    finally:
        if original is None:
            os.environ.pop("GSTPRO_BOOTSTRAP", None)
        else:
            os.environ["GSTPRO_BOOTSTRAP"] = original


def case_masters():
    headers = production_headers()

    response = client.get(
        "/api/products?company_id=demo-company",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert any(item.get("id") for item in response.json())

    response = client.get(
        "/api/gstins?company_id=demo-company",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert any(
        item.get("gstin") == "33ABCDE1234F1Z5"
        for item in response.json()
    )


def invoice_payload(series, number):
    return {
        "invoice_type": "TAX_INVOICE",
        "scheme": "REGULAR",
        "supplier_state_code": "33",
        "place_of_supply": "33",
        "supplier_gstin": "33ABCDE1234F1Z5",
        "customer_gstin": "33AACFA1234A1Z1",
        "customer_name": "ABC Traders",
        "invoice_date": "2026-09-21",
        "series": series,
        "invoice_number": number,
        "lines": [{
            "product_id": "P1",
            "description": "Cotton Shirt",
            "hsn_sac": "620520",
            "unit": "PCS",
            "qty": 1,
            "rate": 500,
            "gst_rate": 18,
        }],
    }


def case_invoice():
    headers = production_headers()

    payload = invoice_payload(
        "PROD",
        f"PROD-TEST-{uuid4().hex[:12]}",
    )

    response = client.post(
        "/api/invoices",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200, response.text

    invoice = response.json()
    invoice_id = invoice["id"]

    assert invoice["status"] == "DRAFT"
    assert invoice["request"]["company_id"]

    fetched = client.get(
        f"/api/invoices/{invoice_id}",
        headers=headers,
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == invoice_id


def case_maker_checker():
    owner = production_headers()
    ca = production_headers("ca@gstpro.local", "caadmin123")

    payload = invoice_payload(
        "PROD-MC",
        f"PROD-MC-{uuid4().hex[:12]}",
    )

    created = client.post(
        "/api/invoices",
        headers=owner,
        json=payload,
    )
    assert created.status_code == 200, created.text
    invoice_id = created.json()["id"]

    submit = client.post(
        f"/api/invoices/{invoice_id}/submit",
        headers=owner,
    )
    assert submit.status_code == 200, submit.text

    self_approve = client.post(
        f"/api/invoices/{invoice_id}/approve",
        headers=owner,
        json={
            "invoice_id": invoice_id,
            "decision": "APPROVE",
        },
    )
    assert self_approve.status_code == 409, self_approve.text

    approve = client.post(
        f"/api/invoices/{invoice_id}/approve",
        headers=ca,
        json={
            "invoice_id": invoice_id,
            "decision": "APPROVE",
        },
    )
    assert approve.status_code == 200, approve.text

    irn = client.post(
        "/api/einvoice/mock",
        headers=owner,
        json={"invoice_id": invoice_id},
    )
    assert irn.status_code == 200, irn.text
    irn_payload = irn.json()
    assert irn_payload["irn"]
    assert irn_payload["status"] == "GENERATED_MOCK"

    duplicate = client.post(
        "/api/einvoice/mock",
        headers=owner,
        json={"invoice_id": invoice_id},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["irn"] == irn_payload["irn"]

    reloaded = client.get(
        f"/api/invoices/{invoice_id}",
        headers=owner,
    )
    assert reloaded.status_code == 200, reloaded.text
    persisted = reloaded.json()["einvoice"]
    assert persisted["irn"] == irn_payload["irn"]
    assert persisted["request_json"]["DocDtls"]["No"] == payload["invoice_number"]

    cancelled = client.post(
        f"/api/einvoice/{invoice_id}/cancel",
        headers=owner,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED_MOCK"

    final = client.get(
        f"/api/invoices/{invoice_id}",
        headers=owner,
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "IRN_CANCELLED"
    assert final.json()["einvoice"]["status"] == "CANCELLED_MOCK"


def case_returns_reconciliation():
    headers = production_headers()
    period = "2026-09"

    imported = client.post(
        "/api/gstr2b/import",
        headers=headers,
        json=[{
            "company_id": "demo-company",
            "gstin_id": "demo-gstin",
            "vendor_gstin": "33AACFA1234A1Z1",
            "vendor_name": "ABC Traders",
            "invoice_number": f"2B-{uuid4().hex[:10]}",
            "invoice_date": "2026-09-21",
            "taxable_value": 1000,
            "cgst": 90,
            "sgst": 90,
            "igst": 0,
            "total": 1180,
        }],
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1

    two_b = client.get(
        f"/api/gstr2b?company_id=demo-company&period={period}",
        headers=headers,
    )
    assert two_b.status_code == 200, two_b.text
    assert any(row["vendor_gstin"] == "33AACFA1234A1Z1" for row in two_b.json())

    recon = client.get(
        f"/api/reconciliation?company_id=demo-company&period={period}",
        headers=headers,
    )
    assert recon.status_code == 200, recon.text
    assert recon.json()["period"] == period
    assert "summary" in recon.json()

    gstr1 = client.get(
        f"/api/returns/gstr1/draft?company_id=demo-company&period={period}",
        headers=headers,
    )
    assert gstr1.status_code == 200, gstr1.text
    assert gstr1.json()["period"] == period
    assert "gstn_payload" in gstr1.json()

    gstr3b = client.get(
        f"/api/returns/gstr3b/draft?company_id=demo-company&period={period}",
        headers=headers,
    )
    assert gstr3b.status_code == 200, gstr3b.text
    assert gstr3b.json()["period"] == period
    assert "net_tax_liability" in gstr3b.json()

    locked = client.post(
        "/api/returns/lock",
        headers=headers,
        json={"gstin_id": "demo-gstin", "return_type": "GSTR1", "period": period},
    )
    assert locked.status_code == 200, locked.text
    assert locked.json()["status"] == "LOCKED"

    listed = client.get("/api/returns?gstin_id=demo-gstin", headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(
        row["return_type"] == "GSTR1" and row["period"] == period and row["status"] == "LOCKED"
        for row in listed.json()
    )


CASES = {
    "ready": case_ready,
    "bootstrap": case_bootstrap,
    "masters": case_masters,
    "invoice": case_invoice,
    "maker_checker": case_maker_checker,
    "returns_reconciliation": case_returns_reconciliation,
}


if __name__ == "__main__":
    case_name = sys.argv[1]
    CASES[case_name]()
