import os
os.environ.setdefault("GSTPRO_MODE", "demo")
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def login(email="admin@gstpro.local", password="admin"):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]

def headers(email="admin@gstpro.local", password="admin"):
    return {"Authorization": f"Bearer {login(email, password)}"}

def test_read_api_is_authenticated_and_tenant_scoped():
    response = client.get("/api/products")
    assert response.status_code == 401
    owner = headers()
    assert client.get("/api/products", headers=owner).status_code == 200
    assert client.get("/api/gstins", headers=owner).status_code == 200
    assert client.get("/api/dashboard", headers=owner).status_code == 200

def test_invalid_and_inactive_authentication_is_rejected():
    assert client.post("/api/auth/login", json={"email": "admin@gstpro.local", "password": "wrong"}).status_code == 401
    from app.main import USERS
    USERS["U1"]["is_active"] = False
    try:
        assert client.post("/api/auth/login", json={"email": "admin@gstpro.local", "password": "admin"}).status_code == 401
    finally:
        USERS["U1"]["is_active"] = True

def test_ready_and_config_contract():
    ready = client.get("/ready")
    assert ready.status_code == 200
    data = ready.json()
    assert data["status"] == "ready"
    assert data["mode"] == "demo"
    config = client.get("/api/config")
    assert config.status_code == 200
    assert "state_codes" in config.json()
    assert config.json()["hsn_min_digits_below_or_equal"] == 4

def test_demo_mode_does_not_claim_process_persistence():
    from app.main import DEMO_MODE, persist_state
    assert DEMO_MODE is True
    persist_state()

def test_end_to_end_invoice_controls_and_audit_chain():
    owner = headers()
    ca = headers("ca@gstpro.local", "caadmin123")
    payload = {
        "invoice_type": "TAX_INVOICE", "scheme": "REGULAR", "supplier_state_code": "33",
        "place_of_supply": "29", "supplier_gstin": "33ABCDE1234F1Z5", "customer_gstin": "29AACFA1234A1Z1",
        "customer_name": "Bharat Karnataka Stores", "invoice_date": "2026-11-20", "series": "L1",
        "invoice_number": "L1/1", "lines": [{"product_id": "P1", "description": "Cotton Shirt", "hsn_sac": "620520",
        "unit": "PCS", "qty": 2, "rate": 500, "gst_rate": 18}], "company_id": "demo-company", "gstin_id": "demo-gstin"
    }
    created = client.post("/api/invoices", headers=owner, json=payload)
    assert created.status_code == 200
    iid = created.json()["id"]
    assert client.post(f"/api/invoices/{iid}/submit", headers=owner).status_code == 200
    assert client.post(f"/api/invoices/{iid}/approve", headers=owner, json={"invoice_id": iid, "decision": "APPROVE"}).status_code == 409
    assert client.post(f"/api/invoices/{iid}/approve", headers=ca, json={"invoice_id": iid, "decision": "APPROVE"}).status_code == 200
    irn = client.post("/api/einvoice/mock", headers=owner, json={"invoice_id": iid})
    assert irn.status_code == 200
    audit = client.get("/api/audit-verify", headers=owner)
    assert audit.status_code == 200
    assert audit.json()["valid"] is True
