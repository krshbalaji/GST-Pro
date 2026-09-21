import os
os.environ.setdefault("GSTPRO_MODE", "demo")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def login(email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]

def payload():
    return {
        "invoice_type": "TAX_INVOICE", "scheme": "REGULAR", "supplier_state_code": "33",
        "place_of_supply": "33", "supplier_gstin": "33ABCDE1234F1Z5", "customer_gstin": "33AACFA1234A1Z1",
        "customer_name": "ABC Traders", "invoice_date": "2026-09-19", "series": "MC", "invoice_number": "MC/1",
        "lines": [{"product_id": "P1", "description": "Cotton Shirt", "hsn_sac": "620520", "unit": "PCS", "qty": 1, "rate": 500, "gst_rate": 18}],
        "reverse_charge": False
    }

def test_maker_checker_before_irn():
    owner = {"Authorization": "Bearer " + login("admin@gstpro.local", "admin")}
    ca = {"Authorization": "Bearer " + login("ca@gstpro.local", "caadmin123")}
    r = client.post("/api/invoices", headers=owner, json=payload())
    assert r.status_code == 200
    iid = r.json()["id"]
    assert client.post("/api/einvoice/mock", headers=owner, json={"invoice_id": iid}).status_code == 409
    assert client.post(f"/api/invoices/{iid}/submit", headers=owner).status_code == 200
    assert client.post(f"/api/invoices/{iid}/approve", headers=owner, json={"invoice_id": iid, "decision": "APPROVE"}).status_code == 409
    assert client.post(f"/api/invoices/{iid}/approve", headers=ca, json={"invoice_id": iid, "decision": "APPROVE"}).status_code == 200
    assert client.post("/api/einvoice/mock", headers=owner, json={"invoice_id": iid}).status_code == 200

def test_audit_chain():
    owner = {"Authorization": "Bearer " + login("admin@gstpro.local", "admin")}
    r = client.get("/api/audit-verify", headers=owner)
    assert r.status_code == 200 and r.json()["valid"] is True
