"""The full per-department pipeline for POST /agents/{dept}/evaluate
(prompt.md 2.6): query own registry -> build facts sheet -> model chooses an
action -> validate & assemble -> persist to the transcript.

This module is deliberately the only place that calls app.llm.decide(). The
engine (app/engine.py) never talks to the model directly -- it only reacts to
the AgentMessage this module returns.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app import facts as facts_mod
from app import llm, validation
from app.db import session

MAX_RETRIES = 1


def agent_name(department: str) -> str:
    return f"{department}_agent"


def department_from_agent_name(name: str) -> str:
    return name[: -len("_agent")] if name.endswith("_agent") else name


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_transcript(case_id: str, thread_id: str) -> list[dict]:
    with session() as conn:
        rows = conn.execute(
            "SELECT payload FROM messages WHERE case_id = ? AND thread_id = ? ORDER BY seq",
            (case_id, thread_id),
        ).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def _persist_message(message: dict) -> None:
    with session() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM messages WHERE case_id = ? AND thread_id = ?",
            (message["case_id"], message["thread_id"]),
        ).fetchone()
        seq = row["m"] + 1
        conn.execute(
            "INSERT INTO messages (case_id, thread_id, seq, from_actor, to_actor, type, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message["case_id"], message["thread_id"], seq,
                message["from"], message["to"], message["type"],
                json.dumps(message), _now(),
            ),
        )


def _assemble(case: dict, department: str, thread_id: str, validated: dict, backend: str, error_reason: str | None) -> dict:
    return {
        "case_id": case["id"],
        "thread_id": thread_id,
        "from": agent_name(department),
        "to": "engine",
        "type": validated["type"],
        "evidence": validated.get("evidence", []),
        "target": agent_name(validated["target"]) if validated.get("target") else None,
        "target_basis": validated.get("target_basis"),
        "sub_tasks": validated.get("sub_tasks", []),
        "missing": validated.get("missing", []),
        "confidence": validated.get("confidence"),
        "rationale": validated.get("rationale", ""),
        "model_backend": backend,
        "error_reason": error_reason,
    }


def evaluate(case: dict, department: str, thread_id: str = "root") -> dict:
    """Runs one full evaluate step for `department` on `case` and returns the
    resulting AgentMessage dict. Always persists the message to the transcript,
    including on `error`, so a failed hop is still auditable."""
    facts = facts_mod.build_facts_sheet(case, department)
    transcript = get_transcript(case["id"], thread_id)

    decision, backend = llm.decide(department, case, facts, transcript)

    last_error: str | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            validated = validation.validate_and_assemble(department, case, facts, decision)
            message = _assemble(case, department, thread_id, validated, backend, None)
            _persist_message(message)
            return message
        except validation.ValidationError as exc:
            last_error = str(exc)
            if attempt < MAX_RETRIES:
                decision, backend = llm.decide(department, case, facts, transcript, retry_feedback=last_error)

    # 2.6 step 5: a model/validation failure must become `error`, never
    # `need_info` -- `need_info` would wrongly make the engine ask the citizen.
    message = _assemble(
        case, department, thread_id,
        {"type": "error", "evidence": [], "target": None, "target_basis": None,
         "sub_tasks": [], "missing": [], "confidence": None, "rationale": ""},
        backend, last_error,
    )
    _persist_message(message)
    return message
