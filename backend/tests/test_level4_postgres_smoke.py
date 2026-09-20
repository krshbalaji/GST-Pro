"""Focused production-PG smoke tests for Level 4.

Run with GSTPRO_RUN_PG_TESTS=1 and DATABASE_URL set.
These tests intentionally use repository APIs so they can be run without a
production API bootstrap/user seed.
"""
import os
from uuid import uuid4
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("GSTPRO_RUN_PG_TESTS") != "1" or not os.getenv("DATABASE_URL"),
    reason="Set GSTPRO_RUN_PG_TESTS=1 and DATABASE_URL to run PostgreSQL integration tests",
)

from app.repositories.postgres import (
    PostgresAuditRepository,
    PostgresCompanyRepository,
    PostgresInvoiceRepository,
    PostgresMasterRepository,
    PostgresApprovalRepository,
    PostgresEInvoiceRepository,
    validate_invoice_transition,
)
from app.storage import store, transaction


@pytest.fixture()
def seeded():
    store.init()
    company_id, gstin_id, maker_id, checker_id, customer_id, product_id = [uuid4() for _ in range(6)]
    company = {"id": str(company_id), "legal_name": "L4 Smoke Co", "pan": "ABCDE1234F", "aato": 45000000, "address": {}}
    gstin = {"id": str(gstin_id), "company_id": str(company_id), "gstin": "33ABCDE1234F1Z5", "state_code": "33", "scheme": "REGULAR"}
    maker = {"id": str(maker_id), "company_id": str(company_id), "name": "Maker", "email": f"maker-{company_id}@test.local", "role": "OWNER", "password_hash": "x"}
    checker = {"id": str(checker_id), "company_id": str(company_id), "name": "Checker", "email": f"checker-{company_id}@test.local", "role": "CA", "password_hash": "x"}
    customer = {"id": str(customer_id), "company_id": str(company_id), "name": "Buyer", "gstin": "29AACFA1234A1Z1", "state_code": "29", "address": {}}
    product = {"id": str(product_id), "company_id": str(company_id), "description": "Item", "hsn_sac": "620520", "unit": "PCS", "rate": 100, "gst_rate": 18, "active": True}
    master = PostgresMasterRepository(store)
    with transaction() as conn:
        PostgresCompanyRepository(store).create(company, conn)
        master.create("gstins", gstin, conn)
        master.create("users", maker, conn)
        master.create("users", checker, conn)
        master.create("customers", customer, conn)
        master.create("products", product, conn)
    yield company_id, gstin_id, maker_id, checker_id, customer_id, product_id
    with transaction() as conn:
        conn.execute("DELETE FROM companies WHERE id=%s", (company_id,))


def invoice_row(ids, number):
    company_id, gstin_id, _, _, customer_id, product_id = ids
    return {
        "id": str(uuid4()),
        "request": {
            "company_id": str(company_id), "gstin_id": str(gstin_id), "supplier_gstin": "33ABCDE1234F1Z5",
            "supplier_state_code": "33", "place_of_supply": "29", "invoice_type": "TAX_INVOICE", "scheme": "REGULAR",
            "invoice_date": "2026-09-21", "series": "L4", "invoice_number": number,
            "customer_gstin": "29AACFA1234A1Z1", "customer_name": "Buyer", "customer_state_code": "29",
            "reverse_charge": False, "customer_id": str(customer_id),
            "original_invoice_id": None,
            "lines": [{"product_id": str(product_id), "description": "Item", "hsn_sac": "620520", "unit": "PCS",
                       "qty": 2, "rate": 100, "gst_rate": 18, "taxable": True}],
        },
        "calculation": {
            "taxable_value": "200", "cgst": "0", "sgst": "0", "igst": "36", "total": "236",
            "lines": [{"product_id": str(product_id), "description": "Item", "hsn_sac": "620520", "unit": "PCS",
                       "qty": 2, "rate": 100, "gst_rate": 18, "taxable": True,
                       "taxable_value": "200", "cgst": "0", "sgst": "0", "igst": "36", "total": "236"}],
        },
        "status": "DRAFT",
    }


def test_atomic_invoice_and_audit_rollback(seeded):
    ids = seeded
    invoice_repo = PostgresInvoiceRepository(store)
    audit_repo = PostgresAuditRepository(store)
    row = invoice_row(ids, "L4/RB")
    with pytest.raises(RuntimeError):
        with transaction() as conn:
            invoice_repo.create(row, conn)
            audit_repo.append({
                "id": str(uuid4()), "company_id": str(ids[0]), "user_id": str(ids[2]),
                "action": "CREATE", "entity_type": "INVOICE", "entity_id": row["id"],
                "old_value": None, "new_value": row,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "previous_hash": "GENESIS", "hash": "forced",
            }, conn)
            raise RuntimeError("rollback")
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM invoices WHERE id=%s", (row["id"],)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM invoice_items WHERE invoice_id=%s", (row["id"],)).fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) AS n FROM audit_logs WHERE entity_id=%s", (row["id"],)).fetchone()["n"] == 0


def test_lifecycle_and_einvoice_persist(seeded):
    ids = seeded
    invoice_repo = PostgresInvoiceRepository(store)
    approval_repo = PostgresApprovalRepository(store)
    einvoice_repo = PostgresEInvoiceRepository(store)
    row = invoice_row(ids, "L4/LIFE")
    with transaction() as conn:
        created = invoice_repo.create(row, conn)
        current = invoice_repo.get_for_update(created["id"], conn)
        invoice_repo.save({**current, "status": "PENDING_APPROVAL"}, conn, expected_status="DRAFT")
        approval_repo.save({
            "invoice_id": created["id"], "status": "PENDING", "submitted_by": str(ids[2]),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }, conn)
        assert validate_invoice_transition("PENDING_APPROVAL", "APPROVED") is None
        current = invoice_repo.get_for_update(created["id"], conn)
        invoice_repo.save({**current, "status": "APPROVED"}, conn, expected_status="PENDING_APPROVAL")
        einvoice_repo.save({
            "invoice_id": created["id"], "irn": "smoke-irn", "irn_date": datetime.now(timezone.utc).isoformat(),
            "ack_no": "1", "signed_qr_payload": "MOCK|smoke-irn", "status": "GENERATED_MOCK",
            "response_json": {"status": "GENERATED_MOCK"},
        }, conn)
    assert invoice_repo.get(created["id"])["status"] == "APPROVED"
    assert einvoice_repo.get(created["id"])["irn"] == "smoke-irn"


def test_duplicate_number_and_immutable_number(seeded):
    ids = seeded
    repo = PostgresInvoiceRepository(store)
    row = invoice_row(ids, "L4/DUP")
    with transaction() as conn:
        first = repo.create(row, conn)
    with pytest.raises(Exception):
        with transaction() as conn:
            repo.create({**row, "id": str(uuid4())}, conn)
    loaded = repo.get(first["id"])
    with pytest.raises(ValueError, match="immutable"):
        with transaction() as conn:
            repo.save({**loaded, "request": {**loaded["request"], "invoice_number": "L4/CHANGED"}}, conn)
