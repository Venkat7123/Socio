import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "devfest.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    address TEXT,
    ward TEXT,
    channel TEXT NOT NULL,
    citizen_ref TEXT NOT NULL,
    owner_department TEXT,
    hop_count INTEGER NOT NULL DEFAULT 0,
    rejected_by TEXT NOT NULL DEFAULT '[]',
    sla_due_at TEXT NOT NULL,
    sla_breached INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(id),
    kind TEXT NOT NULL,
    url TEXT NOT NULL,
    transcript TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    from_agent TEXT NOT NULL,
    type TEXT NOT NULL,
    target_department TEXT,
    reason TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '[]',
    target_basis TEXT,
    confidence REAL,
    missing TEXT NOT NULL DEFAULT '[]',
    sub_tasks TEXT NOT NULL DEFAULT '[]',
    model_backend TEXT,
    sub_task_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sub_tasks (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    department TEXT NOT NULL,
    task TEXT NOT NULL,
    status TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    target_basis TEXT,
    rationale TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sub_tasks_case ON sub_tasks(case_id);
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(id),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wa_messages (
    provider_message_id TEXT PRIMARY KEY,
    phone TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wa_conversations (
    phone TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'idle',
    draft TEXT NOT NULL DEFAULT '{}',
    case_id TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wa_case_links (
    phone TEXT NOT NULL,
    case_id TEXT NOT NULL REFERENCES cases(id),
    role TEXT NOT NULL,
    provider TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (phone, case_id)
);
CREATE TABLE IF NOT EXISTS wa_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    provider TEXT NOT NULL,
    body TEXT NOT NULL,
    media TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wa_notified (
    phone TEXT NOT NULL,
    case_id TEXT NOT NULL,
    key TEXT NOT NULL,
    PRIMARY KEY (phone, case_id, key)
);
CREATE TABLE IF NOT EXISTS route_claims (
    case_id TEXT PRIMARY KEY,
    claimed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_case ON messages(case_id);
CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_log(case_id);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after the first release; init_db adds them to a database created before they existed.
MESSAGE_COLUMNS = {
    "target_basis": "TEXT", "confidence": "REAL", "missing": "TEXT NOT NULL DEFAULT '[]'",
    "sub_tasks": "TEXT NOT NULL DEFAULT '[]'", "model_backend": "TEXT", "sub_task_id": "TEXT",
}


def init_db(path: Path | str = DB_PATH) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        have = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
        for col, decl in MESSAGE_COLUMNS.items():
            if col not in have:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {col} {decl}")
