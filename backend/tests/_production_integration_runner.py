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


CASES = {
    "ready": case_ready,
    "bootstrap": case_bootstrap,
    "masters": case_masters,
    "invoice": case_invoice,
    "maker_checker": case_maker_checker,
}


if __name__ == "__main__":
    case_name = sys.argv[1]
    CASES[case_name]()
