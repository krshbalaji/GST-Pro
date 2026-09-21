import os
os.environ.setdefault("GSTPRO_MODE","demo")
from app.main import app
from app.repositories.postgres import INVOICE_STATES, validate_invoice_transition

def test_level4_lifecycle_state_machine():
    validate_invoice_transition("DRAFT","PENDING_APPROVAL")
    validate_invoice_transition("PENDING_APPROVAL","APPROVED")
    validate_invoice_transition("PENDING_APPROVAL","REJECTED")
    validate_invoice_transition("APPROVED","EINVOICE_GENERATED")
    validate_invoice_transition("EINVOICE_GENERATED","IRN_CANCELLED")
    for current,target in [("DRAFT","APPROVED"),("APPROVED","DRAFT"),("CANCELLED","DRAFT")]:
        try:
            validate_invoice_transition(current,target)
            assert False, f"{current}->{target} should fail"
        except ValueError:
            pass

def test_level4_atomic_transaction_contract_present():
    import app.repositories.postgres as p
    assert hasattr(p,"PostgresTransactionRepository")
    src=open(p.__file__,encoding="utf-8").read()
    assert "conn.commit()" in src
    assert "conn.rollback()" in src
    assert 'FOR UPDATE' in src

def test_invoice_schema_has_number_uniqueness():
    from pathlib import Path
    schema=(Path(__file__).parents[2]/"database"/"schema.sql").read_text(encoding="utf-8")
    assert "unique(gstin_id,series,number)" in schema
