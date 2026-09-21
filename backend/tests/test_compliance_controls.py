import os
os.environ.setdefault("GSTPRO_MODE", "demo")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
TOKEN = client.post("/api/auth/login", json={"email": "admin@gstpro.local", "password": "admin"}).json()["access_token"]
HEAD = {"Authorization": "Bearer " + TOKEN}

def invoice_payload(number="LOCK-1"):
    return {"invoice_type":"TAX_INVOICE","scheme":"REGULAR","supplier_state_code":"33","place_of_supply":"33","supplier_gstin":"33ABCDE1234F1Z5","customer_gstin":"33AACFA1234A1Z1","customer_name":"ABC Traders","invoice_date":"2026-10-05","series":"SDE","invoice_number":number,"lines":[{"product_id":"P1","description":"Cotton Shirt","hsn_sac":"620520","unit":"PCS","qty":1,"rate":500,"gst_rate":18}]}

def test_locked_period_blocks_new_invoice():
    r = client.post("/api/returns/lock",headers=HEAD,json={"gstin_id":"demo-gstin","return_type":"GSTR1","period":"2026-10"})
    assert r.status_code==200
    r = client.post("/api/invoices",headers=HEAD,json=invoice_payload())
    assert r.status_code==409
