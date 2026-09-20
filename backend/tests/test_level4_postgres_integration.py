import os
from uuid import uuid4
from decimal import Decimal

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
)
from app.storage import store, transaction


def seed():
    company_id=uuid4()
    gstin_id=uuid4()
    user_id=uuid4()
    ca_id=uuid4()
    customer_id=uuid4()
    product_id=uuid4()
    company={"id":str(company_id),"legal_name":"Level4 Test Co","trade_name":"L4","pan":"ABCDE1234F","aato":45000000,"address":{}}
    gstin={"id":str(gstin_id),"company_id":str(company_id),"gstin":"33ABCDE1234F1Z5","state_code":"33","scheme":"REGULAR","legal_name":"Level4 Test Co","trade_name":"L4","address":{}}
    user={"id":str(user_id),"company_id":str(company_id),"name":"Maker","email":f"maker-{company_id}@test.local","role":"OWNER","password_hash":"x"}
    ca={"id":str(ca_id),"company_id":str(company_id),"name":"Checker","email":f"checker-{company_id}@test.local","role":"CA","password_hash":"x"}
    customer={"id":str(customer_id),"company_id":str(company_id),"name":"Buyer","gstin":"29AACFA1234A1Z1","state_code":"29","address":{}}
    product={"id":str(product_id),"company_id":str(company_id),"description":"Test Item","hsn_sac":"620520","unit":"PCS","rate":100,"gst_rate":18,"active":True}
    master=PostgresMasterRepository(store)
    with transaction() as conn:
        PostgresCompanyRepository(store).create(company,conn)
        master.create("gstins",gstin,conn)
        master.create("users",user,conn)
        master.create("users",ca,conn)
        master.create("customers",customer,conn)
        master.create("products",product,conn)
    return company_id,gstin_id,user_id,ca_id,customer_id,product_id


@pytest.fixture()
def seeded():
    ids=seed()
    yield ids
    company_id=ids[0]
    with transaction() as conn:
        conn.execute("DELETE FROM companies WHERE id=%s",(company_id,))


def invoice_row(company_id,gstin_id,customer_id,product_id,number="L4/1", original_invoice_id=None, invoice_type="TAX_INVOICE"):
    return {
        "id":str(uuid4()),
        "request":{
            "company_id":str(company_id),"gstin_id":str(gstin_id),"supplier_gstin":"33ABCDE1234F1Z5",
            "supplier_state_code":"33","place_of_supply":"29","invoice_type":invoice_type,"scheme":"REGULAR",
            "invoice_date":"2026-09-21","series":"L4","invoice_number":number,"customer_gstin":"29AACFA1234A1Z1",
            "customer_name":"Buyer","customer_state_code":"29","reverse_charge":False,
            "customer_id":str(customer_id),"original_invoice_id":str(original_invoice_id) if original_invoice_id else None,
            "lines":[{"product_id":str(product_id),"description":"Test Item","hsn_sac":"620520","unit":"PCS","qty":2,"rate":100,"gst_rate":18,"taxable":True},
            ],
        },
        "calculation":{"taxable_value":"200","cgst":"0","sgst":"0","igst":"36","total":"236",
                       "lines":[{"product_id":str(product_id),"description":"Test Item","hsn_sac":"620520","unit":"PCS",
                                 "qty":2,"rate":100,"gst_rate":18,"taxable":True,"taxable_value":"200",
                                 "cgst":"0","sgst":"0","igst":"36","total":"236"}]},
        "status":"DRAFT",
    }


def test_invoice_create_persists_header_items_and_customer(seeded):
    company_id,gstin_id,user_id,ca_id,customer_id,product_id=seeded
    repo=PostgresInvoiceRepository(store)
    row=invoice_row(company_id,gstin_id,customer_id,product_id)
    with transaction() as conn:
        created=repo.create(row,conn)
        assert created["status"]=="DRAFT"
        assert len(created["calculation"]["lines"])==1
        assert conn.execute("SELECT count(*) AS n FROM invoice_items WHERE invoice_id=%s",(created["id"],)).fetchone()["n"]==1


def test_duplicate_number_is_rejected_and_immutable(seeded):
    company_id,gstin_id,user_id,ca_id,customer_id,product_id=seeded
    repo=PostgresInvoiceRepository(store)
    row=invoice_row(company_id,gstin_id,customer_id,product_id,number="L4/DUP")
    with transaction() as conn:
        first=repo.create(row,conn)
    with pytest.raises(Exception):
        with transaction() as conn:
            repo.create({**row,"id":str(uuid4())},conn)
    loaded=repo.get(first["id"])
    with pytest.raises(ValueError):
        with transaction() as conn:
            repo.save({**loaded,"request":{**loaded["request"],"series":"CHANGED"}},conn,immutable=True)


def test_lifecycle_and_maker_checker_are_concurrency_guarded(seeded):
    company_id,gstin_id,user_id,ca_id,customer_id,product_id=seeded
    repo=PostgresInvoiceRepository(store); approvals=PostgresApprovalRepository(store)
    audit=PostgresAuditRepository(store)
    row=invoice_row(company_id,gstin_id,customer_id,product_id,number="L4/LIFE")
    with transaction() as conn:
        created=repo.create(row,conn)
        current=repo.get_for_update(created["id"],conn)
        repo.save({**current,"status":"PENDING_APPROVAL"},conn,expected_status="DRAFT")
        approval=approvals.save({"invoice_id":created["id"],"status":"PENDING","submitted_by":str(user_id),"submitted_at":"2026-09-21T00:00:00+00:00"},conn)
        assert approval["status"]=="PENDING"
    assert repo.get(created["id"])["status"]=="PENDING_APPROVAL"
    with pytest.raises(ValueError):
        from app.repositories.postgres import validate_invoice_transition
        validate_invoice_transition("DRAFT","EINVOICE_GENERATED")


def test_transaction_rolls_back_invoice_items_and_audit(seeded):
    company_id,gstin_id,user_id,ca_id,customer_id,product_id=seeded
    repo=PostgresInvoiceRepository(store); audit=PostgresAuditRepository(store)
    row=invoice_row(company_id,gstin_id,customer_id,product_id,number="L4/RB")
    invoice_id=row["id"]
    with pytest.raises(RuntimeError):
        with transaction() as conn:
            repo.create(row,conn)
            audit.append({
                "id":str(uuid4()),"company_id":str(company_id),"user_id":str(user_id),
                "action":"CREATE","entity_type":"INVOICE","entity_id":invoice_id,
                "old_value":None,"new_value":row,"created_at":"2026-09-21T00:00:00+00:00",
                "previous_hash":"GENESIS","hash":"forced-test-hash"
            },conn)
            raise RuntimeError("forced rollback")
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) AS n FROM invoices WHERE id=%s",(invoice_id,)).fetchone()["n"]==0
        assert conn.execute("SELECT count(*) AS n FROM invoice_items WHERE invoice_id=%s",(invoice_id,)).fetchone()["n"]==0
        assert conn.execute("SELECT count(*) AS n FROM audit_logs WHERE entity_id=%s",(invoice_id,)).fetchone()["n"]==0


def test_credit_note_links_same_company_original(seeded):
    company_id,gstin_id,user_id,ca_id,customer_id,product_id=seeded
    repo=PostgresInvoiceRepository(store)
    original=invoice_row(company_id,gstin_id,customer_id,product_id,number="L4/ORIG")
    with transaction() as conn:
        original=repo.create(original,conn)
    note=invoice_row(company_id,gstin_id,customer_id,product_id,number="L4/CRN",original_invoice_id=original["id"],invoice_type="CREDIT_NOTE")
    with transaction() as conn:
        created=repo.create(note,conn)
    assert created["request"]["original_invoice_id"]==original["id"]
