"""Supabase (hosted Postgres) access layer via psycopg2.

Every other module (app/registries.py, app/engine.py, app/agents.py,
app/query_log.py, app/routers/admin.py, seed_db.py) was written against a
sqlite3-shaped API: `with session() as conn: conn.execute(sql, params)`,
`?`-style placeholders, and dict-like row access (`row["x"]`, `dict(row)`).
`_Connection` below reproduces exactly that surface on top of a real
psycopg2/Postgres connection -- translating `?` -> `%s` and returning
RealDictCursor rows (already dict-like) -- so none of those call sites needed
to change when the storage engine did.

Schema notes:
  - Each department's registry is its own set of tables (own asset types,
    own history, own handovers). There is no cross-department table or view,
    which is what makes "agents can only query their own registry" true at
    the storage level, not just by convention in application code.
  - query_log is shared infrastructure (not asset data) -- it is how refs are
    minted and later validated as belonging to (department, case_id).
  - cases / messages / sub_tasks hold the case lifecycle and full transcript.
  - All tables live in config.DB_SCHEMA, a dedicated Postgres schema (not
    "public") inside the Supabase project, so this app's data never collides
    with Supabase's own dashboard/PostgREST conventions.
"""
from __future__ import annotations

from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.config import DATABASE_URL, DB_SCHEMA

SCHEMA = """
CREATE TABLE IF NOT EXISTS corporation_roads (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, length_m REAL, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS corporation_drains (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS corporation_lamps (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS corporation_garbage_points (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS corporation_handovers (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, asset_type TEXT, receiving_department TEXT,
    order_ref TEXT, note TEXT, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS corporation_history (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, category TEXT, outcome TEXT, created_at TEXT,
    ward TEXT, synthetic INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS water_board_pipelines (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, zone TEXT, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS water_board_valves (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, zone TEXT, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS water_board_history (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, category TEXT, outcome TEXT, created_at TEXT,
    ward TEXT, synthetic INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS electricity_poles (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS electricity_transformers (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS electricity_feeders (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS electricity_history (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, category TEXT, outcome TEXT, created_at TEXT,
    ward TEXT, synthetic INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS highways_segments (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, road_name TEXT, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS highways_bridges (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, ward TEXT, synthetic INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS highways_history (
    id TEXT PRIMARY KEY, lat REAL, lng REAL, category TEXT, outcome TEXT, created_at TEXT,
    ward TEXT, synthetic INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS query_log (
    ref TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    department TEXT NOT NULL,
    tool TEXT NOT NULL,
    params TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_query_log_case_dept ON query_log(case_id, department);

CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    ward TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    accuracy_m REAL,
    description TEXT,
    point_label TEXT,
    status TEXT NOT NULL,
    owner_department TEXT,
    last_department TEXT,
    linked_case_id TEXT,
    hop_count INTEGER NOT NULL DEFAULT 0,
    escalation_reason TEXT,
    needs_info_fields TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    from_actor TEXT NOT NULL,
    to_actor TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_case ON messages(case_id, thread_id, seq);

CREATE TABLE IF NOT EXISTS sub_tasks (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    parent_thread_id TEXT NOT NULL,
    department TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL,
    depends_on TEXT,
    target_basis TEXT,
    rationale TEXT,
    hop_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS adjudications (
    id SERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    proposed_owner TEXT,
    confidence REAL,
    reasoning TEXT,
    trigger_reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. Copy .env.example to .env and fill in your Supabase "
                "connection string (Project Settings -> Database -> Connection string -> URI)."
            )
        _pool = psycopg2.pool.ThreadedConnectionPool(
            1, 10, dsn=DATABASE_URL, options=f"-c search_path={DB_SCHEMA},public"
        )
    return _pool


class _Connection:
    """Gives a pooled psycopg2 connection the sqlite3.Connection.execute()
    shorthand and `?`-style placeholders the rest of the app is written
    against. None of this codebase's SQL literals contain a bare '?' or '%'
    outside of placeholder position, so the translation below is safe."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql: str, params=()):
        cur = self._raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def executescript(self, sql: str) -> None:
        cur = self._raw.cursor()
        cur.execute(sql)
        cur.close()

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()


@contextmanager
def session():
    pool = _get_pool()
    raw = pool.getconn()
    conn = _Connection(raw)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(raw)


def init_db(reset: bool = False) -> None:
    with session() as conn:
        if reset:
            conn.execute(f'DROP SCHEMA IF EXISTS "{DB_SCHEMA}" CASCADE')
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"')
        conn.executescript(SCHEMA)


def is_empty() -> bool:
    with session() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM corporation_roads").fetchone()
        return row["c"] == 0
