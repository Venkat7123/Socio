"""Orchestrates the case lifecycle: initial routing, the accept/reject/split/
need_info/error loop per thread, hop counting, dispute resolution and
escalation. This is "the engine" the agent messages in prompt.md 2.7 are
addressed `to`.

Engine rules implemented here (6-8 are given verbatim by prompt.md 2.6; 1-5
were not in the provided spec fragment -- sections 1-2.3 were not available --
so they are inferred from the worked scenarios in 2.7 and called out below):

  [inferred] A case is first looked up in routing_seed.json for an initial
             department + confidence. >= threshold -> status ROUTED, below
             -> status DISPUTE. Either way the initial department's agent
             still evaluates with its own registry (2.7 S1: "0 hops" only
             because the seeded department's own agent accepted; the seed
             itself never assigns ownership on its own).
  [inferred] Hop cap (config.HOP_CAP, default 3): exceeding it escalates.
  2. A reject cannot send the case back to a department already in
     rejected_by unless it carries new (strong: presence/handover_record)
     evidence not seen before in the thread.
  6. A department becomes an owner only on its own accept (or its own part
     of a split) backed by presence evidence -- enforced already by
     app.validation, so the engine only ever sees a validated accept here.
  7. If every matrix candidate for the category has rejected absence-only,
     escalate immediately, bypassing the hop cap.
  8. A split does not count as a hop. A rejected proposed sub-task runs the
     same protocol on its own thread, with its own hop count.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app import agents, adjudicator, matrix
from app.config import HOP_CAP, ROUTING_THRESHOLD, DUPLICATE_RADIUS_M
from app.config import ROUTING_SEED_PATH, DATA_DIR
from app.db import session
from app.geo import distance_m
from app.schemas import CaseCreate, CaseInfoReply

with open(ROUTING_SEED_PATH, encoding="utf-8") as f:
    _ROUTING_SEED = json.load(f)

with open(DATA_DIR / "seed_points.json", encoding="utf-8") as f:
    _SEED_POINTS = json.load(f)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# --------------------------------------------------------------------------- #
# Location / routing lookups
# --------------------------------------------------------------------------- #

def _resolve_location(payload: CaseCreate) -> tuple[float, float, str, str | None]:
    if payload.point_label:
        point = _SEED_POINTS["points"].get(payload.point_label)
        if not point:
            raise ValueError(f"unknown point_label '{payload.point_label}'")
        return point["lat"], point["lng"], _SEED_POINTS["ward"], payload.point_label
    if payload.lat is None or payload.lng is None:
        raise ValueError("either point_label or both lat and lng must be provided")
    return payload.lat, payload.lng, payload.ward, None


def _try_resolve_location(payload: CaseCreate) -> tuple[float, float, str] | None:
    """Non-raising variant of _resolve_location, used only for the duplicate
    check below -- a ticket with no usable location at all simply can't be
    deduplicated by location, which is fine; it falls through to the normal
    create_case path and whatever that does with a missing location."""
    try:
        lat, lng, ward, _ = _resolve_location(payload)
        return lat, lng, ward
    except ValueError:
        return None


def _find_duplicate(category: str, lat: float, lng: float, ward: str) -> str | None:
    """Duplicate-ticket linking (not in the original spec fragment): two
    tickets of the same category within DUPLICATE_RADIUS_M of each other are
    treated as the same physical complaint. Only matches against root cases
    (linked_case_id IS NULL) so duplicates never chain to other duplicates --
    every DUPLICATE_LINKED case points directly at the original report, and
    a duplicate can never itself become a match target."""
    with session() as conn:
        rows = conn.execute(
            "SELECT id, lat, lng FROM cases WHERE category = ? AND ward = ? AND linked_case_id IS NULL",
            (category, ward),
        ).fetchall()
    best_id, best_dist = None, DUPLICATE_RADIUS_M
    for r in rows:
        d = distance_m(lat, lng, r["lat"], r["lng"])
        if d <= best_dist:
            best_dist, best_id = d, r["id"]
    return best_id


def _routing_lookup(category: str, ward: str, point_label: str | None) -> tuple[str | None, float]:
    """Returns (department, confidence). department is None when the matrix/
    seed says this category must go straight to a human triager."""
    if point_label:
        for ov in _ROUTING_SEED.get("overrides", []):
            if ov["point"] == point_label and ov["category"] == category:
                return ov["department"], ov["confidence"]
    for row in _ROUTING_SEED["rows"]:
        if row["category"] == category and row["ward"] == ward:
            if row.get("action") == "escalate_to_human_triager" or row.get("department") is None:
                return None, 0.0
            return row["department"], row["confidence"]
    return None, 0.0


# --------------------------------------------------------------------------- #
# Thread-level dispute loop (shared by the root case thread and every
# sub-task thread spawned by a split)
# --------------------------------------------------------------------------- #

def _compute_rejected_by(transcript: list[dict]) -> dict[str, list[dict]]:
    rejected: dict[str, list[dict]] = {}
    for m in transcript:
        if m["type"] == "reject":
            dept = agents.department_from_agent_name(m["from"])
            rejected.setdefault(dept, []).append(m)
    return rejected


def _is_absence_only(message: dict) -> bool:
    return all(e["kind"] in ("absence", "jurisdiction_rule", "history") for e in message.get("evidence", []))


def _all_absence_only(rejected_by: dict[str, list[dict]], candidates_overall: list[str]) -> bool:
    if not candidates_overall:
        return False
    for dept in candidates_overall:
        msgs = rejected_by.get(dept)
        if not msgs or not all(_is_absence_only(m) for m in msgs):
            return False
    return True


def _has_new_strong_evidence(message: dict) -> bool:
    return any(e["kind"] in ("presence", "handover_record") for e in message.get("evidence", []))


def _run_thread(case: dict, thread_id: str, department: str, hop_count: int) -> dict:
    current_dept = department
    hops = hop_count
    for _ in range(HOP_CAP + len(matrix.departments()) + 2):  # hard safety bound
        message = agents.evaluate(case, current_dept, thread_id)
        mtype = message["type"]

        if mtype == "accept":
            return {"outcome": "accept", "department": current_dept, "hop_count": hops, "message": message}
        if mtype == "need_info":
            return {
                "outcome": "need_info", "department": current_dept, "hop_count": hops,
                "missing": message["missing"], "message": message,
            }
        if mtype == "error":
            return {
                "outcome": "error", "department": current_dept, "hop_count": hops,
                "escalation_reason": message.get("error_reason") or "model/validation error", "message": message,
            }
        if mtype == "split":
            return {
                "outcome": "split", "department": current_dept, "hop_count": hops,
                "sub_tasks_raw": message["sub_tasks"], "message": message,
            }

        # reject
        transcript = agents.get_transcript(case["id"], thread_id)
        rejected_by = _compute_rejected_by(transcript)
        candidates_overall = matrix.candidates_for_category(case["category"])

        if _all_absence_only(rejected_by, candidates_overall):
            adjudication = adjudicator.adjudicate(transcript, candidates_overall)
            return {
                "outcome": "escalated", "department": current_dept, "hop_count": hops,
                "escalation_reason": "return blocked, all candidates absence-only",
                "adjudication": adjudication, "message": message,
            }

        target_dept = agents.department_from_agent_name(message["target"]) if message.get("target") else None
        if target_dept is None:
            return {
                "outcome": "error", "department": current_dept, "hop_count": hops,
                "escalation_reason": "reject message had no resolvable target", "message": message,
            }

        if target_dept in rejected_by and not _has_new_strong_evidence(message):
            adjudication = adjudicator.adjudicate(transcript, candidates_overall)
            return {
                "outcome": "escalated", "department": current_dept, "hop_count": hops,
                "escalation_reason": "return blocked, no new evidence",
                "adjudication": adjudication, "message": message,
            }

        new_hops = hops + 1
        if new_hops > HOP_CAP:
            adjudication = adjudicator.adjudicate(transcript, candidates_overall)
            return {
                "outcome": "escalated", "department": current_dept, "hop_count": new_hops,
                "escalation_reason": "hop cap reached",
                "adjudication": adjudication, "message": message,
            }

        hops = new_hops
        current_dept = target_dept

    return {"outcome": "error", "department": current_dept, "hop_count": hops, "escalation_reason": "safety loop limit exceeded"}


# --------------------------------------------------------------------------- #
# Persistence helpers
# --------------------------------------------------------------------------- #

def _persist_adjudication(case_id: str, thread_id: str, adjudication: dict, trigger_reason: str) -> None:
    with session() as conn:
        conn.execute(
            "INSERT INTO adjudications (case_id, thread_id, proposed_owner, confidence, reasoning, trigger_reason, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                case_id, thread_id, adjudication.get("proposed_owner"), adjudication.get("confidence"),
                adjudication.get("reasoning"), trigger_reason, _now(),
            ),
        )


def _update_case(case_id: str, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with session() as conn:
        conn.execute(f"UPDATE cases SET {cols} WHERE id = ?", (*fields.values(), case_id))


def _insert_sub_task(case_id: str, thread_id: str, parent_thread_id: str, department: str, task: str,
                      status: str, depends_on: str | None, target_basis: str | None, rationale: str | None) -> str:
    sid = _new_id("T")
    now = _now()
    with session() as conn:
        conn.execute(
            "INSERT INTO sub_tasks (id, case_id, thread_id, parent_thread_id, department, task, status, "
            "depends_on, target_basis, rationale, hop_count, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (sid, case_id, thread_id, parent_thread_id, department, task, status,
             depends_on, target_basis, rationale, now, now),
        )
    return sid


def _update_sub_task(sub_task_id: str, **fields) -> None:
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with session() as conn:
        conn.execute(f"UPDATE sub_tasks SET {cols} WHERE id = ?", (*fields.values(), sub_task_id))


_SUBTASK_TERMINAL_STATUS = {
    "accept": "ASSIGNED", "need_info": "NEEDS_INFO", "error": "ERROR",
    "escalated": "ESCALATED", "split": "SPLIT",
}
_CASE_TERMINAL_STATUS = {
    "accept": "ASSIGNED", "need_info": "NEEDS_INFO", "error": "ERROR",
    "escalated": "ESCALATED", "split": "SPLIT",
}

# Not specified by the provided spec fragment. A split proposing a sub-task
# that itself splits again is architecturally legal (rule 8 lets a rejected
# proposed sub-task run the full protocol on its own thread, and a thread can
# end in split), but nothing bounds how deep that can nest. This is a
# defensive cap, independent of prompt quality, against a pathological model
# sequence recursing indefinitely.
MAX_SPLIT_DEPTH = 2


def _materialize_split(case: dict, parent_thread_id: str, owning_department: str, sub_tasks_raw: list[dict],
                        is_root: bool, depth: int = 1) -> None:
    own = next((s for s in sub_tasks_raw if s["department"] == owning_department), None)
    own_id = None
    if own:
        own_thread = f"{case['id']}-{_new_id('sub')}"
        own_id = _insert_sub_task(
            case["id"], own_thread, parent_thread_id, owning_department, own["task"],
            "ASSIGNED", None, own.get("target_basis"), own.get("rationale"),
        )

    for s in sub_tasks_raw:
        if s["department"] == owning_department:
            continue
        thread_id = f"{case['id']}-{_new_id('sub')}"
        sid = _insert_sub_task(
            case["id"], thread_id, parent_thread_id, s["department"], s["task"],
            "PROPOSED", own_id, s.get("target_basis"), s.get("rationale"),
        )
        outcome = _run_thread(case, thread_id, s["department"], hop_count=0)
        status = _SUBTASK_TERMINAL_STATUS.get(outcome["outcome"], "ESCALATED")
        _update_sub_task(sid, status=status, hop_count=outcome["hop_count"])
        if outcome["outcome"] == "escalated":
            _persist_adjudication(case["id"], thread_id, outcome["adjudication"], outcome["escalation_reason"])
        elif outcome["outcome"] == "split":
            if depth >= MAX_SPLIT_DEPTH:
                transcript = agents.get_transcript(case["id"], thread_id)
                candidates_overall = matrix.candidates_for_category(case["category"])
                adjudication = adjudicator.adjudicate(transcript, candidates_overall)
                _persist_adjudication(case["id"], thread_id, adjudication, "split depth cap reached")
                _update_sub_task(sid, status="ESCALATED")
            else:
                _materialize_split(case, thread_id, outcome["department"], outcome["sub_tasks_raw"],
                                    is_root=False, depth=depth + 1)


def _apply_root_outcome(case: dict, outcome: dict) -> None:
    case_id = case["id"]
    status = _CASE_TERMINAL_STATUS.get(outcome["outcome"], "ESCALATED")
    if outcome["outcome"] == "accept":
        _update_case(case_id, status=status, owner_department=outcome["department"], hop_count=outcome["hop_count"])
    elif outcome["outcome"] == "need_info":
        _update_case(
            case_id, status=status, hop_count=outcome["hop_count"], last_department=outcome["department"],
            needs_info_fields=json.dumps(outcome["missing"]),
        )
    elif outcome["outcome"] == "error":
        _update_case(case_id, status=status, hop_count=outcome["hop_count"], escalation_reason=outcome["escalation_reason"])
    elif outcome["outcome"] == "escalated":
        _update_case(case_id, status=status, hop_count=outcome["hop_count"], escalation_reason=outcome["escalation_reason"])
        _persist_adjudication(case_id, "root", outcome["adjudication"], outcome["escalation_reason"])
    elif outcome["outcome"] == "split":
        _update_case(case_id, status=status, owner_department=outcome["department"], hop_count=outcome["hop_count"])
        _materialize_split(case, "root", outcome["department"], outcome["sub_tasks_raw"], is_root=True)


# --------------------------------------------------------------------------- #
# Public API used by routers
# --------------------------------------------------------------------------- #

def create_case(payload: CaseCreate) -> str:
    category = payload.category
    case_id = _new_id("C")
    now = _now()

    # Duplicate check runs first, before any routing/matrix/agent work, for
    # EVERY category (including "other" and categories with no routing seed
    # entry) -- a second report of the same complaint shouldn't re-trigger a
    # second human-triage escalation either. It only applies when the ticket
    # has a usable location at all; one with none falls through untouched.
    loc = _try_resolve_location(payload)
    if loc is not None:
        dup_lat, dup_lng, dup_ward = loc
        existing_id = _find_duplicate(category, dup_lat, dup_lng, dup_ward)
        if existing_id is not None:
            original = get_case(existing_id)
            with session() as conn:
                conn.execute(
                    "INSERT INTO cases (id, category, ward, lat, lng, accuracy_m, description, point_label, "
                    "status, owner_department, linked_case_id, hop_count, escalation_reason, needs_info_fields, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'DUPLICATE_LINKED', ?, ?, 0, NULL, NULL, ?, ?)",
                    (case_id, category, dup_ward, dup_lat, dup_lng, payload.accuracy_m, payload.description,
                     payload.point_label, original.get("owner_department"), existing_id, now, now),
                )
            return case_id

    candidates_overall = matrix.candidates_for_category(category)

    if not candidates_overall:
        lat = payload.lat or 0.0
        lng = payload.lng or 0.0
        with session() as conn:
            conn.execute(
                "INSERT INTO cases (id, category, ward, lat, lng, accuracy_m, description, point_label, "
                "status, owner_department, hop_count, escalation_reason, needs_info_fields, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ESCALATED', NULL, 0, ?, NULL, ?, ?)",
                (case_id, category, payload.ward, lat, lng, payload.accuracy_m, payload.description,
                 payload.point_label, f"category '{category}' has no matrix candidates; requires human triage", now, now),
            )
        return case_id

    lat, lng, ward, point_label = _resolve_location(payload)
    dept0, seed_conf = _routing_lookup(category, ward, point_label)

    if dept0 is None:
        with session() as conn:
            conn.execute(
                "INSERT INTO cases (id, category, ward, lat, lng, accuracy_m, description, point_label, "
                "status, owner_department, hop_count, escalation_reason, needs_info_fields, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ESCALATED', NULL, 0, ?, NULL, ?, ?)",
                (case_id, category, ward, lat, lng, payload.accuracy_m, payload.description, point_label,
                 f"no routing seed entry for category '{category}' in ward '{ward}'", now, now),
            )
        return case_id

    status0 = "ROUTED" if seed_conf >= ROUTING_THRESHOLD else "DISPUTE"
    with session() as conn:
        conn.execute(
            "INSERT INTO cases (id, category, ward, lat, lng, accuracy_m, description, point_label, "
            "status, owner_department, hop_count, escalation_reason, needs_info_fields, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL, NULL, ?, ?)",
            (case_id, category, ward, lat, lng, payload.accuracy_m, payload.description, point_label, status0, now, now),
        )

    case = get_case(case_id)
    outcome = _run_thread(case, "root", dept0, hop_count=0)
    _apply_root_outcome(case, outcome)
    return case_id


def resume_with_info(case_id: str, reply: CaseInfoReply) -> None:
    case = get_case(case_id)
    if case["status"] != "NEEDS_INFO":
        raise ValueError(f"case {case_id} is not awaiting info (status={case['status']})")

    updates: dict = {"status": "DISPUTE", "needs_info_fields": None}
    if reply.exact_location:
        if "lat" in reply.exact_location:
            updates["lat"] = reply.exact_location["lat"]
        if "lng" in reply.exact_location:
            updates["lng"] = reply.exact_location["lng"]
        if "accuracy_m" in reply.exact_location:
            updates["accuracy_m"] = reply.exact_location["accuracy_m"]
    _update_case(case_id, **updates)

    case = get_case(case_id)
    resume_department = case["last_department"] or case["category"]
    outcome = _run_thread(case, "root", resume_department, hop_count=case["hop_count"])
    _apply_root_outcome(case, outcome)


def get_case(case_id: str) -> dict:
    with session() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not row:
        raise KeyError(f"case {case_id} not found")
    d = dict(row)
    d["needs_info_fields"] = json.loads(d["needs_info_fields"]) if d.get("needs_info_fields") else []
    return d


def get_case_out(case_id: str) -> dict:
    case = get_case(case_id)
    with session() as conn:
        msg_rows = conn.execute(
            "SELECT * FROM messages WHERE case_id = ? ORDER BY thread_id, seq", (case_id,)
        ).fetchall()
        sub_rows = conn.execute("SELECT * FROM sub_tasks WHERE case_id = ?", (case_id,)).fetchall()
        adj_rows = conn.execute("SELECT * FROM adjudications WHERE case_id = ?", (case_id,)).fetchall()

    transcript = [json.loads(r["payload"]) for r in msg_rows]
    sub_tasks = [
        {
            "id": r["id"], "department": r["department"], "task": r["task"], "status": r["status"],
            "depends_on": r["depends_on"], "target_basis": r["target_basis"], "rationale": r["rationale"],
            "hop_count": r["hop_count"],
        }
        for r in sub_rows
    ]
    adjudications = [
        {
            "thread_id": r["thread_id"], "proposed_owner": r["proposed_owner"], "confidence": r["confidence"],
            "reasoning": r["reasoning"], "trigger_reason": r["trigger_reason"], "created_at": r["created_at"],
        }
        for r in adj_rows
    ]

    return {**case, "transcript": transcript, "sub_tasks": sub_tasks, "adjudications": adjudications}


def list_cases(status: str | None = None) -> list[dict]:
    with session() as conn:
        if status:
            rows = conn.execute("SELECT * FROM cases WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["needs_info_fields"] = json.loads(d["needs_info_fields"]) if d.get("needs_info_fields") else []
        out.append(d)
    return out
