import os
os.environ["GSTPRO_MODE"] = "demo"
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_ready_reports_demo_mode():
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["mode"] == "demo"


def test_protected_master_reads_require_authentication():
    r = client.get("/api/products")
    assert r.status_code == 401
