import os
from pathlib import Path
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")


class PersistentStore:
    """PostgreSQL connection/schema utility. Normalized tables are the operational source of truth."""

    def __init__(self):
        self.enabled = bool(DATABASE_URL)
        self.conninfo = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1) if DATABASE_URL else None

    def connect(self):
        import psycopg
        from psycopg.rows import dict_row
        if not self.conninfo:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(self.conninfo, row_factory=dict_row)

    def init(self):
        if not self.enabled:
            return
        configured = os.getenv("GSTPRO_SCHEMA_PATH")
        candidates = []
        if configured:
            candidates.append(Path(configured))
        candidates.extend([
            Path("/app/schema.sql"),
            Path(__file__).resolve().parents[2] / "database" / "schema.sql",
            Path(__file__).resolve().parents[1] / "schema.sql",
        ])
        schema = next((path for path in candidates if path.exists()), candidates[0])
        if not schema.exists():
            raise RuntimeError(f"Schema file not found. Checked: {candidates}")
        with self.connect() as conn:
            conn.execute(schema.read_text(encoding="utf-8"))
            conn.commit()

    def health(self):
        if not self.enabled:
            return {"enabled": False, "status": "memory"}
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1")
            return {"enabled": True, "status": "ok"}
        except Exception as exc:
            return {"enabled": True, "status": "error", "detail": str(exc)}


store = PersistentStore()


@contextmanager
def transaction():
    conn = store.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
