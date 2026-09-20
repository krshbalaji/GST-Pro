import os
from pathlib import Path
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")

class PersistentStore:
    """PostgreSQL connection/schema utility. Normalized tables are the operational source of truth."""
    def __init__(self):
        self.enabled = bool(DATABASE_URL)
        self.conninfo = DATABASE_URL.replace("postgresql+psycopg://","postgresql://",1) if DATABASE_URL else None

    def connect(self):
        import psycopg
        if not self.conninfo:
            raise RuntimeError("DATABASE_URL is not configured")
        return psycopg.connect(self.conninfo)

    def init(self):
        if not self.enabled:
            return
        schema = Path(os.getenv("GSTPRO_SCHEMA_PATH","/app/schema.sql"))
        if not schema.exists():
            raise RuntimeError(f"Schema file not found: {schema}")
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
