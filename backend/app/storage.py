import json, os
from pathlib import Path
from contextlib import contextmanager

DATABASE_URL = os.getenv('DATABASE_URL')

class PersistentStore:
    def __init__(self):
        self.enabled = bool(DATABASE_URL)
        self.conninfo = DATABASE_URL.replace('postgresql+psycopg://','postgresql://',1) if DATABASE_URL else None

    def connect(self):
        import psycopg
        return psycopg.connect(self.conninfo)

    def init(self):
        if not self.enabled: return
        schema=Path(os.getenv('GSTPRO_SCHEMA_PATH','/app/schema.sql'))
        with self.connect() as conn:
            if schema.exists():
                conn.execute(schema.read_text())
            else:
                conn.execute('CREATE TABLE IF NOT EXISTS app_state (key text primary key, value jsonb not null, updated_at timestamptz default now())')
            conn.commit()

    def health(self):
        if not self.enabled: return {'enabled':False,'status':'memory'}
        try:
            with self.connect() as conn: conn.execute('SELECT 1')
            return {'enabled':True,'status':'ok'}
        except Exception as exc:
            return {'enabled':True,'status':'error','detail':str(exc)}

    def load(self):
        if not self.enabled: return {}
        with self.connect() as conn:
            rows=conn.execute('SELECT key,value FROM app_state').fetchall()
        return {k:v for k,v in rows}

    def save(self, state):
        if not self.enabled: return
        with self.connect() as conn:
            for key,value in state.items():
                conn.execute('INSERT INTO app_state(key,value,updated_at) VALUES(%s,%s,now()) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()', (key,json.dumps(value,default=str)))
            conn.commit()

store=PersistentStore()
