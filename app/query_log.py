"""Every tool call a department agent makes is logged here with a `ref`.

Per prompt.md 2.5: "A `ref` is valid only for the department and case that
produced it." This module is what makes that enforceable: validation.py
looks refs up scoped to (department, case_id) and rejects anything else,
including refs that are syntactically fine but belong to another department
or another case.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.db import session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(case_id: str, department: str, tool: str, params: dict, result: dict) -> str:
    ref = f"q-{uuid.uuid4().hex[:8]}"
    with session() as conn:
        conn.execute(
            "INSERT INTO query_log (ref, case_id, department, tool, params, result, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ref, case_id, department, tool, json.dumps(params), json.dumps(result), _now()),
        )
    return ref


def get(ref: str, case_id: str, department: str) -> dict | None:
    with session() as conn:
        row = conn.execute(
            "SELECT * FROM query_log WHERE ref = ? AND case_id = ? AND department = ?",
            (ref, case_id, department),
        ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def get_many(refs: list[str], case_id: str, department: str) -> dict[str, dict]:
    """Returns only the refs that validly belong to (department, case_id).
    Callers must check len(result) == len(refs) to detect a bad/foreign ref."""
    found: dict[str, dict] = {}
    for ref in refs:
        entry = get(ref, case_id, department)
        if entry:
            found[ref] = entry
    return found


def all_for_case_department(case_id: str, department: str) -> list[dict]:
    with session() as conn:
        rows = conn.execute(
            "SELECT * FROM query_log WHERE case_id = ? AND department = ? ORDER BY created_at",
            (case_id, department),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "ref": row["ref"],
        "case_id": row["case_id"],
        "department": row["department"],
        "tool": row["tool"],
        "params": json.loads(row["params"]),
        "result": json.loads(row["result"]),
        "created_at": row["created_at"],
    }
