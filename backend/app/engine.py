"""Case engine: state machine, SLA clock, dispute-message rules, audit log. Pure functions over a sqlite connection."""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from .llm import ModelUnavailable
from .models import (
    SLA, AgentMessage, AuditEntry, Case, CaseCreate, CaseStatus, ConfirmRequest, Department, Location,
    MediaItem, MessageType, Severity, SubTask, SubTaskStatus, VerifyRequest, VerifyResult,
)

HOP_CAP = 2

SLA_HOURS = {Severity.critical: 4, Severity.high: 24, Severity.medium: 48, Severity.low: 72}

S = CaseStatus
TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    S.need_info: {S.new},
    S.new: {S.in_dispute, S.assigned, S.escalated},
    S.in_dispute: {S.in_dispute, S.assigned, S.escalated},
    S.assigned: {S.in_dispute, S.in_progress, S.escalated},
    S.in_progress: {S.pending_verification, S.escalated},
    S.pending_verification: {S.awaiting_citizen, S.in_progress, S.escalated},
    S.awaiting_citizen: {S.closed, S.reopened},
    S.reopened: {S.in_dispute, S.assigned, S.in_progress, S.escalated},
    S.escalated: {S.assigned, S.in_progress},
    S.closed: set(),
}
# Statuses in which departments may post dispute messages.
DISPUTE_OPEN = {S.new, S.in_dispute, S.assigned, S.reopened}
# Statuses the SLA sweep escalates when the deadline passes (others are only flagged).
SLA_ESCALATES = {S.new, S.in_dispute, S.assigned, S.in_progress, S.reopened}
SLA_FLAG_ONLY = {S.pending_verification, S.awaiting_citizen}


class EngineError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _audit(conn: sqlite3.Connection, case_id: str, actor: str, action: str, detail: dict, at: datetime) -> None:
    conn.execute(
        "INSERT INTO audit_log (id, case_id, actor, action, detail, at) VALUES (?, ?, ?, ?, ?, ?)",
        (_new_id("aud"), case_id, actor, action, json.dumps(detail), at.isoformat()),
    )


def check_transition(current: CaseStatus, new: CaseStatus) -> None:
    if new not in TRANSITIONS[current]:
        raise EngineError(409, f"Illegal transition {current.value} -> {new.value}")


def _row_to_case(conn: sqlite3.Connection, row: sqlite3.Row) -> Case:
    media = conn.execute(
        "SELECT kind, url, transcript FROM media WHERE case_id = ? ORDER BY id", (row["id"],)
    ).fetchall()
    return Case(
        id=row["id"],
        status=row["status"],
        category=row["category"],
        severity=row["severity"],
        description=row["description"],
        location=Location(lat=row["lat"], lng=row["lng"], address=row["address"], ward=row["ward"]),
        media=[MediaItem(**dict(m)) for m in media],
        channel=row["channel"],
        citizen_ref=row["citizen_ref"],
        owner_department=row["owner_department"],
        hop_count=row["hop_count"],
        rejected_by=json.loads(row["rejected_by"]),
        sla=SLA(due_at=row["sla_due_at"], breached=bool(row["sla_breached"])),
        sub_tasks=list_sub_tasks(conn, row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _load_row(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        raise EngineError(404, f"Case {case_id} not found")
    return row


def sweep_sla(conn: sqlite3.Connection, now: datetime | None = None) -> None:
    """Flag overdue cases as breached and escalate the ones still in the department phase."""
    now = now or _now()
    rows = conn.execute("SELECT id, status, sla_due_at FROM cases WHERE sla_breached = 0 AND status != 'closed'").fetchall()
    for r in rows:
        if datetime.fromisoformat(r["sla_due_at"]) >= now:
            continue
        status = CaseStatus(r["status"])
        if status in SLA_ESCALATES:
            conn.execute(
                "UPDATE cases SET sla_breached = 1, status = ?, updated_at = ? WHERE id = ?",
                (S.escalated.value, now.isoformat(), r["id"]),
            )
            _audit(conn, r["id"], "engine", "sla_breached", {"from_status": status.value, "to_status": "escalated"}, now)
        elif status in SLA_FLAG_ONLY or status == S.escalated:
            conn.execute("UPDATE cases SET sla_breached = 1, updated_at = ? WHERE id = ?", (now.isoformat(), r["id"]))
            _audit(conn, r["id"], "engine", "sla_breached", {"status": status.value}, now)
    conn.commit()


def create_case(conn: sqlite3.Connection, body: CaseCreate, now: datetime | None = None) -> Case:
    now = now or _now()
    case_id = _new_id("case")
    due = now + timedelta(hours=SLA_HOURS[body.severity])
    loc = body.location
    conn.execute(
        """INSERT INTO cases (id, status, category, severity, description, lat, lng, address, ward, channel,
                              citizen_ref, owner_department, hop_count, rejected_by, sla_due_at, sla_breached,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, '[]', ?, 0, ?, ?)""",
        (case_id, S.new.value, body.category.value, body.severity.value, body.description, loc.lat, loc.lng,
         loc.address, loc.ward, body.channel.value, body.citizen_ref, due.isoformat(), now.isoformat(), now.isoformat()),
    )
    for m in body.media:
        conn.execute("INSERT INTO media (case_id, kind, url, transcript) VALUES (?, ?, ?, ?)",
                     (case_id, m.kind, m.url, m.transcript))
    _audit(conn, case_id, "intake", "case_created",
           {"category": body.category.value, "severity": body.severity.value, "sla_due_at": due.isoformat()}, now)
    conn.commit()
    return _row_to_case(conn, _load_row(conn, case_id))


def get_case(conn: sqlite3.Connection, case_id: str, now: datetime | None = None) -> Case:
    sweep_sla(conn, now)
    return _row_to_case(conn, _load_row(conn, case_id))


def list_cases(
    conn: sqlite3.Connection,
    status: CaseStatus | None = None,
    ward: str | None = None,
    department: Department | None = None,
    limit: int = 50,
    now: datetime | None = None,
) -> list[Case]:
    sweep_sla(conn, now)
    where, args = [], []
    if status:
        where.append("status = ?")
        args.append(status.value)
    if ward:
        where.append("ward = ?")
        args.append(ward)
    if department:
        where.append("owner_department = ?")
        args.append(department.value)
    sql = "SELECT * FROM cases" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    rows = conn.execute(sql, (*args, limit)).fetchall()
    return [_row_to_case(conn, r) for r in rows]


def _row_to_message(r: sqlite3.Row) -> AgentMessage:
    return AgentMessage(
        id=r["id"], case_id=r["case_id"], sub_task_id=r["sub_task_id"], from_agent=r["from_agent"], type=r["type"],
        target_department=r["target_department"], target_basis=r["target_basis"], reason=r["reason"],
        evidence=json.loads(r["evidence"]), confidence=r["confidence"], sub_tasks=json.loads(r["sub_tasks"]),
        missing=json.loads(r["missing"]), model_backend=r["model_backend"], created_at=r["created_at"],
    )


def list_messages(conn: sqlite3.Connection, case_id: str, include_sub_tasks: bool = False) -> list[AgentMessage]:
    """Case-thread messages. The dispute protocol only ever looks at these; sub-task threads are separate."""
    _load_row(conn, case_id)
    where = "case_id = ?" + ("" if include_sub_tasks else " AND sub_task_id IS NULL")
    rows = conn.execute(f"SELECT * FROM messages WHERE {where} ORDER BY created_at, rowid", (case_id,)).fetchall()
    return [_row_to_message(r) for r in rows]


def list_sub_tasks(conn: sqlite3.Connection, case_id: str) -> list[SubTask]:
    rows = conn.execute("SELECT * FROM sub_tasks WHERE case_id = ? ORDER BY created_at, rowid", (case_id,)).fetchall()
    return [SubTask(**dict(r)) for r in rows]


def list_audit(conn: sqlite3.Connection, case_id: str) -> list[AuditEntry]:
    _load_row(conn, case_id)
    rows = conn.execute("SELECT * FROM audit_log WHERE case_id = ? ORDER BY at, rowid", (case_id,)).fetchall()
    return [
        AuditEntry(id=r["id"], case_id=r["case_id"], actor=r["actor"], action=r["action"],
                   detail=json.loads(r["detail"]), at=r["at"])
        for r in rows
    ]


def audit_event(conn: sqlite3.Connection, case_id: str, actor: str, action: str, detail: dict, now: datetime | None = None) -> None:
    """Write an audit entry for something the routing layer did (not a state change)."""
    _audit(conn, case_id, actor, action, detail, now or _now())
    conn.commit()


def escalate_case(conn: sqlite3.Connection, case_id: str, reason: str, actor: str = "engine", now: datetime | None = None) -> Case:
    """Send a case to a human when no department can own it (e.g. a category with no candidates). Uses the normal
    state machine: only states that may escalate can."""
    now = now or _now()
    case = _row_to_case(conn, _load_row(conn, case_id))
    check_transition(case.status, S.escalated)
    conn.execute("UPDATE cases SET status = ?, updated_at = ? WHERE id = ?", (S.escalated.value, now.isoformat(), case_id))
    _audit(conn, case_id, actor, "escalated", {"reason": reason, "from_status": case.status.value}, now)
    conn.commit()
    return _row_to_case(conn, _load_row(conn, case_id))


def _insert_message(conn: sqlite3.Connection, m: AgentMessage, now: datetime) -> None:
    conn.execute(
        "INSERT INTO messages (id, case_id, from_agent, type, target_department, target_basis, reason, evidence, "
        "confidence, missing, sub_tasks, model_backend, sub_task_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (m.id, m.case_id, m.from_agent.value, m.type.value, m.target_department.value if m.target_department else None,
         m.target_basis, m.reason, json.dumps([e.model_dump() for e in m.evidence]), m.confidence,
         json.dumps(m.missing), json.dumps([t.model_dump(mode="json") for t in m.sub_tasks]), m.model_backend,
         m.sub_task_id, now.isoformat()),
    )


def _current_holder(prior: list[AgentMessage]) -> Department | None:
    """Department the case was last referred to, if the last referral is still unanswered."""
    for m in reversed(prior):
        if m.type in (MessageType.reject, MessageType.transfer):
            return m.target_department
        if m.type == MessageType.accept:
            return None
    return None


def post_message(
    conn: sqlite3.Connection, case_id: str, msg: AgentMessage, now: datetime | None = None
) -> AgentMessage:
    """Apply a department agent message to a case, enforcing the dispute protocol."""
    now = now or _now()
    sweep_sla(conn, now)
    case = _row_to_case(conn, _load_row(conn, case_id))
    prior = list_messages(conn, case_id)

    if case.status not in DISPUTE_OPEN:
        raise EngineError(409, f"Case is {case.status.value}; no dispute messages accepted")
    if case.status == S.assigned and msg.from_agent != case.owner_department:
        raise EngineError(409, f"Case is owned by {case.owner_department.value}; only the owner may post")
    if case.status == S.in_dispute:
        holder = _current_holder(prior)
        if holder is not None and msg.from_agent != holder:
            raise EngineError(409, f"Case was referred to {holder.value}; only they may respond")

    new_status, owner = case.status, case.owner_department
    hop_count, rejected_by = case.hop_count, list(case.rejected_by)
    audit_action = f"message_{msg.type.value}"
    audit_detail: dict = {"from": msg.from_agent.value, "reason": msg.reason}

    if msg.type == MessageType.accept:
        new_status, owner = S.assigned, msg.from_agent
    elif msg.type in (MessageType.reject, MessageType.transfer):
        target = msg.target_department
        seen_refs = {e.ref for m in prior for e in m.evidence}
        if target in case.rejected_by and not any(e.ref not in seen_refs for e in msg.evidence):
            raise EngineError(409, f"{target.value} already rejected this case; new evidence is required to re-send it")
        owner = None
        if msg.from_agent not in rejected_by:
            rejected_by.append(msg.from_agent)
        audit_detail["target"] = target.value
        if hop_count >= HOP_CAP:
            new_status = S.escalated
            audit_action = "escalated_hop_cap"
        else:
            hop_count += 1
            new_status = S.in_dispute
            audit_detail["hop_count"] = hop_count
    elif msg.type == MessageType.escalate:
        new_status = S.escalated
    # request_info leaves the state unchanged

    if new_status != case.status:
        check_transition(case.status, new_status)

    saved = msg.model_copy(update={"id": _new_id("msg"), "case_id": case_id, "created_at": now})
    _insert_message(conn, saved, now)
    conn.execute(
        "UPDATE cases SET status = ?, owner_department = ?, hop_count = ?, rejected_by = ?, updated_at = ? WHERE id = ?",
        (new_status.value, owner.value if owner else None, hop_count, json.dumps([d.value for d in rejected_by]),
         now.isoformat(), case_id),
    )
    if new_status != case.status:
        audit_detail["status"] = new_status.value
    _audit(conn, case_id, msg.from_agent.value, audit_action, audit_detail, now)
    for t in msg.sub_tasks:  # proposals stay `proposed` until the target department accepts
        sid = _new_id("sub")
        conn.execute(
            "INSERT INTO sub_tasks (id, case_id, department, task, status, proposed_by, target_basis, rationale, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, case_id, t.department.value, t.task, SubTaskStatus.proposed.value, msg.from_agent.value,
             t.target_basis, t.rationale, now.isoformat(), now.isoformat()),
        )
        _audit(conn, case_id, msg.from_agent.value, "sub_task_proposed",
               {"sub_task_id": sid, "department": t.department.value, "task": t.task, "target_basis": t.target_basis}, now)
    conn.commit()
    return saved


_SUB_TASK_OUTCOME = {
    MessageType.accept: SubTaskStatus.assigned,
    MessageType.request_info: SubTaskStatus.needs_info,
    MessageType.reject: SubTaskStatus.escalated,
    MessageType.transfer: SubTaskStatus.escalated,
    MessageType.escalate: SubTaskStatus.escalated,
}


def post_sub_task_message(
    conn: sqlite3.Connection, case_id: str, sub_task_id: str, msg: AgentMessage, now: datetime | None = None
) -> AgentMessage:
    """The target department answers a proposed sub-task. Only that department may answer, and only while it is
    `proposed`. An accept assigns it; anything else leaves it for a human (escalated) or for more information."""
    now = now or _now()
    _load_row(conn, case_id)
    row = conn.execute("SELECT * FROM sub_tasks WHERE id = ? AND case_id = ?", (sub_task_id, case_id)).fetchone()
    if row is None:
        raise EngineError(404, f"Sub-task {sub_task_id} not found on case {case_id}")
    if row["status"] != SubTaskStatus.proposed.value:
        raise EngineError(409, f"Sub-task is {row['status']}; only a proposed sub-task can be answered")
    if msg.from_agent.value != row["department"]:
        raise EngineError(409, f"Sub-task belongs to {row['department']}; only that department may answer")
    if msg.sub_tasks:
        raise EngineError(409, "A sub-task answer cannot propose further sub-tasks")

    outcome = _SUB_TASK_OUTCOME[msg.type]
    saved = msg.model_copy(update={"id": _new_id("msg"), "case_id": case_id, "sub_task_id": sub_task_id, "created_at": now})
    _insert_message(conn, saved, now)
    conn.execute("UPDATE sub_tasks SET status = ?, updated_at = ? WHERE id = ?", (outcome.value, now.isoformat(), sub_task_id))
    _audit(conn, case_id, msg.from_agent.value, f"sub_task_{outcome.value}",
           {"sub_task_id": sub_task_id, "message_type": msg.type.value, "reason": msg.reason}, now)
    conn.commit()
    return saved


VERIFIABLE = {S.assigned, S.in_progress, S.reopened}


def verify_case(conn: sqlite3.Connection, case_id: str, req: VerifyRequest, agent, now: datetime | None = None) -> VerifyResult:
    """Run the verification agent on a crew's after-photo. A pass moves the case to awaiting_citizen;
    a fail leaves it in_progress so the crew can resubmit. The agent runs before any state is written,
    so an agent failure leaves the case untouched."""
    now = now or _now()
    sweep_sla(conn, now)
    case = _row_to_case(conn, _load_row(conn, case_id))
    if case.status not in VERIFIABLE:
        raise EngineError(409, f"Case is {case.status.value}; verification needs an assigned, in-progress or reopened case")

    try:
        verdict = agent.verify(case, req)
    except ModelUnavailable as e:
        # Nothing is decided and the case state is untouched; the crew is told to resubmit.
        _audit(conn, case_id, "engine", "verification_unavailable", {"reason": str(e)}, now)
        conn.commit()
        return VerifyResult(
            case_id=case_id, gps_ok=False, distance_m=0.0, vision_same_spot=False, vision_resolved=False,
            reason="Verification is temporarily unavailable. Please resubmit the photo in a minute.",
            passed=False, status=case.status, retry=True,
        )

    if case.status != S.in_progress:
        check_transition(case.status, S.in_progress)
    check_transition(S.in_progress, S.pending_verification)
    final = S.awaiting_citizen if verdict.passed else S.in_progress
    check_transition(S.pending_verification, final)

    conn.execute("UPDATE cases SET status = ?, updated_at = ? WHERE id = ?", (final.value, now.isoformat(), case_id))
    _audit(conn, case_id, "field_crew", "verification_passed" if verdict.passed else "verification_failed", {
        "from_status": case.status.value, "status": final.value, "after_photo_url": req.after_photo_url,
        "gps_ok": verdict.gps_ok, "distance_m": verdict.distance_m,
        "vision_same_spot": verdict.vision_same_spot, "vision_resolved": verdict.vision_resolved, "reason": verdict.reason,
    }, now)
    conn.commit()
    return VerifyResult(
        case_id=case_id, gps_ok=verdict.gps_ok, distance_m=verdict.distance_m,
        vision_same_spot=verdict.vision_same_spot, vision_resolved=verdict.vision_resolved,
        reason=verdict.reason, passed=verdict.passed, status=final,
    )


def confirm_case(conn: sqlite3.Connection, case_id: str, req: ConfirmRequest, now: datetime | None = None) -> Case:
    """Citizen closes the case (resolved) or reopens it."""
    now = now or _now()
    sweep_sla(conn, now)
    case = _row_to_case(conn, _load_row(conn, case_id))
    if case.status != S.awaiting_citizen:
        raise EngineError(409, f"Case is {case.status.value}; only a verified case awaiting the citizen can be confirmed")
    new_status = S.closed if req.resolved else S.reopened
    check_transition(case.status, new_status)
    conn.execute("UPDATE cases SET status = ?, updated_at = ? WHERE id = ?", (new_status.value, now.isoformat(), case_id))
    _audit(conn, case_id, "citizen", "confirmed_closed" if req.resolved else "reopened",
           {"status": new_status.value, "comment": req.comment}, now)
    conn.commit()
    return _row_to_case(conn, _load_row(conn, case_id))
