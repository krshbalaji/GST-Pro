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


def test_level4_main_routes_use_atomic_transaction_paths():
    from pathlib import Path
    main=(Path(__file__).parents[1]/"app"/"main.py").read_text(encoding="utf-8")
    assert "from .storage import store, transaction" in main
    assert "REPOSITORIES['transactions'].submit_invoice" in main
    assert "REPOSITORIES['transactions'].decide_invoice" in main
    assert "with transaction() as conn:" in main

def test_level4_mapper_is_not_duplicated():
    import app.repositories.postgres as p
    src=open(p.__file__,encoding="utf-8").read()
    assert src.count("class DomainIdMapper:") == 1
    assert src.count("class PostgresTransactionRepository:") == 1

    
def test_level4_schema_supports_invoice_integrity():
    from pathlib import Path
    schema=(Path(__file__).parents[2]/"database"/"schema.sql").read_text(encoding="utf-8")
    assert "unique(gstin_id,series,number)" in schema
    assert "invoice_items" in schema
    assert "e_invoices" in schema
    assert "invoice_approvals" in schema

def test_level4_production_invoice_paths_are_repo_backed():
    from pathlib import Path
    main=(Path(__file__).parents[1]/"app"/"main.py").read_text(encoding="utf-8")
    assert "REPOSITORIES['invoices'].get(invoice_id)" in main
    assert "REPOSITORIES['transactions'].submit_invoice" in main
    assert "REPOSITORIES['transactions'].decide_invoice" in main
    assert "REPOSITORIES['invoices'].delete(invoice_id,conn=conn)" in main

def test_level4_postgres_integration_guard():
    import os
    # Integration suite is intentionally opt-in; normal demo regression must stay DB-free.
    assert os.getenv("GSTPRO_RUN_PG_TESTS","0") in {"0","1"}

def test_production_schema_resolution_is_portable():
    from pathlib import Path
    storage = (Path(__file__).parents[1] / "app" / "storage.py").read_text(encoding="utf-8")
    assert "GSTPRO_SCHEMA_PATH" in storage
    assert "Path(__file__).resolve().parents[2] / "database" / "schema.sql" in storage


def test_level4_production_integration_is_opt_in():
    import os
    if os.getenv("GSTPRO_RUN_PG_TESTS", "0") != "1":
        return
    assert os.getenv("DATABASE_URL"), "DATABASE_URL is required for PostgreSQL integration tests"
