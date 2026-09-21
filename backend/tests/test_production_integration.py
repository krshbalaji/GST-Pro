import os
import subprocess
import sys
from pathlib import Path


RUNNER = Path(__file__).with_name("_production_integration_runner.py")


def run_production_case(case):
    env = os.environ.copy()
    env["GSTPRO_MODE"] = "production"
    env.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://gstpro:gstpro@localhost:5432/gstpro",
    )

    result = subprocess.run(
        [sys.executable, str(RUNNER), case],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, (
        f"Production integration case {case!r} failed.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )


def test_production_ready_and_database():
    run_production_case("ready")


def test_production_bootstrap_is_opt_in():
    run_production_case("bootstrap")


def test_production_domain_id_mapping_for_auth_and_masters():
    run_production_case("masters")


def test_production_invoice_create_and_read():
    run_production_case("invoice")


def test_production_maker_checker_transaction_path():
    run_production_case("maker_checker")
