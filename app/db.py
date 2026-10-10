"""SQLite access layer. Plain sqlite3 (stdlib) -- no ORM needed for a hackathon demo.

Schema notes:
  - Each department's registry is its own set of tables (own asset types,
    own history, own handovers). There is no cross-department table or view,
    which is what makes "agents can only query their own registry" true at
    the storage level, not just by convention in application code.
  - query_log is shared infrastructure (not asset data) -- it is how refs are
    minted and later validated as belonging to (department, case_id).
  - cases / messages / sub_tasks hold the case lifecycle and full transcript.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import DB_PATH

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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    proposed_owner TEXT,
    confidence REAL,
    reasoning TEXT,
    trigger_reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(reset: bool = False) -> None:
    if reset and Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    with session() as conn:
        conn.executescript(SCHEMA)


def is_empty() -> bool:
    with session() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM corporation_roads").fetchone()
        return row["c"] == 0
