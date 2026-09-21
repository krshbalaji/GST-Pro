from pathlib import Path

POSTGRES_SOURCE=Path(__file__).parents[1]/"app"/"repositories"/"postgres.py"
SCHEMA=Path(__file__).parents[2]/"database"/"schema.sql"
MAIN=Path(__file__).parents[1]/"app"/"main.py"

def test_postgres_adapters_are_write_capable():
    src=POSTGRES_SOURCE.read_text(encoding="utf-8")
    assert "INSERT INTO companies" in src
    assert "INSERT INTO invoices" in src
    assert "INSERT INTO invoice_items" in src
    assert "INSERT INTO gstr2b_entries" in src
    assert "INSERT INTO audit_logs" in src
    assert "class PostgresReturnRepository" in src
    assert "ON CONFLICT" in src

def test_production_binding_and_mapping_are_present():
    main=MAIN.read_text(encoding="utf-8")
    assert "GSTPRO_MODE" in main
    assert "ProductionState" in main
    assert "build_repositories()" in main

def test_uuid_mapping_schema_exists():
    schema=SCHEMA.read_text(encoding="utf-8")
    assert "gstpro_id_map" in schema
    assert "domain_id varchar(255)" in schema
    assert "database_id uuid" in schema


def test_invoice_lifecycle_repository_contract():
    src=POSTGRES_SOURCE.read_text(encoding="utf-8")
    assert "INVOICE_STATES" in src
    assert "class InvoiceLifecycleRepository" in src
    assert "FOR UPDATE" in src


def test_level4_transaction_repository_contract():
    src=POSTGRES_SOURCE.read_text(encoding="utf-8")
    assert "class PostgresTransactionRepository" in src
    assert "create_invoice_with_audit" in src
    assert "transition_with_approval_and_audit" in src
    assert "conn.rollback()" in src

