from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
TOKEN = client.post("/api/auth/login", json={"email": "admin@gstpro.local", "password": "admin"}).json()["access_token"]
HEAD = {"Authorization": "Bearer " + TOKEN}

def test_gstr2b_import_and_reconciliation_match():
    p = client.post("/api/purchases", headers=HEAD, json={
        "vendor_name": "Test Vendor", "vendor_gstin": "33ABCDE1234F1Z9", "invoice_number": "P-100",
        "invoice_date": "2026-09-10", "taxable_value": 1000, "cgst": 90, "sgst": 90, "igst": 0, "total": 1180
    })
    assert p.status_code == 200
    r = client.post("/api/gstr2b/import", headers=HEAD, json=[{
        "vendor_gstin": "33ABCDE1234F1Z9", "vendor_name": "Test Vendor", "invoice_number": "P-100",
        "invoice_date": "2026-09-10", "taxable_value": 1000, "cgst": 90, "sgst": 90, "igst": 0, "total": 1180
    }])
    assert r.status_code == 200
    rows = client.get("/api/reconciliation?period=2026-09", headers=HEAD).json()["rows"]
    match = [x for x in rows if x.get("invoice_no") == "P-100"]
    assert match and match[0]["bucket"] == "OK"
