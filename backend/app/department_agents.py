"""Adapter between the engine and the Track C department agents.

The engine depends only on `call_department_agent(department, case, transcript, sub_task) -> AgentMessage`. This module
hides everything about Track C: the HTTP call, its message format, and its quirks. Whatever happens (a valid answer,
bad output, a timeout, an LLM error, an unreachable service) the caller gets a valid AgentMessage in OUR contract.
It never raises for an agent problem.

Hard rules checked here before the engine sees a message (they are Track C's rules, preserved as defence in depth):
  * a reject names a target that is a candidate for the case's category in the shared jurisdiction matrix, is not the
    rejecting department, carries evidence, and cites a target_basis that really supports the target;
  * an accept carries presence evidence from the department's own registry;
  * a reject backed only by absence has its confidence capped at 0.70;
  * sub-task proposals name other departments that are candidates, with a valid basis.
Evidence refs are rebuilt from the kind and the normalized finding text, so the same finding always gets the same ref.
"""
import hashlib
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Protocol

import httpx
from pydantic import ValidationError

from . import shared_config
from .models import AgentMessage, Case, Department, MessageType, SubTask

TRACKC_URL = os.environ.get("TRACKC_URL", "http://localhost:8100")
AGENT_TIMEOUT_S = float(os.environ.get("AGENT_TIMEOUT_S", "15"))
TRACKC_MODE = os.environ.get("TRACKC_MODE", "inline")  # "inline" (stateless endpoint) or "legacy" (TEMPORARY, below)
TRACKC_DB_PATH = os.environ.get("TRACKC_DB_PATH", "")  # legacy mode only

ABSENCE_ONLY_KINDS = {"absence", "jurisdiction_rule", "history"}
ABSENCE_ONLY_CAP = 0.70
EVIDENCE_KINDS = {"presence", "absence", "handover_record", "jurisdiction_rule", "history"}
TYPE_FROM_TRACKC = {"accept": MessageType.accept, "reject": MessageType.reject, "split": MessageType.accept,
                    "need_info": MessageType.request_info}
TYPE_TO_TRACKC = {MessageType.accept: "accept", MessageType.reject: "reject", MessageType.transfer: "reject",
                  MessageType.request_info: "need_info"}


class AgentUnavailable(Exception):
    """The agent could not be reached or did not answer in time. `kind` is timeout | unreachable | http_error."""

    def __init__(self, kind: str, detail: str):
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail


class InvalidAgentOutput(Exception):
    """Track C answered, but not with something that satisfies our contract and rules. `kind` is llm_error | invalid_output."""

    def __init__(self, detail: str, kind: str = "invalid_output"):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


# --------------------------------------------------------------------------------------------- stable evidence refs
def normalize_finding(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).rstrip(".")


def stable_ref(department: str, kind: str, finding: str) -> str:
    """The same finding always gets the same ref, however many times (and in whatever query) an agent cites it."""
    digest = hashlib.sha1(normalize_finding(finding).encode("utf-8")).hexdigest()[:10]
    return f"{department}:{kind}:{digest}"


# ------------------------------------------------------------------------------------------------------- transports
class TrackCClient(Protocol):
    def evaluate(self, department: str, case: dict, transcript: list[dict], thread_id: str) -> dict: ...


class HttpTrackCClient:
    """Calls the stateless endpoint: POST /agents/{dept}/evaluate-inline (see integration/trackc-owner.patch)."""

    def __init__(self, base_url: str = TRACKC_URL, timeout: float = AGENT_TIMEOUT_S, transport: httpx.BaseTransport | None = None):
        self.http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(timeout, connect=5), transport=transport)

    def evaluate(self, department: str, case: dict, transcript: list[dict], thread_id: str) -> dict:
        try:
            r = self.http.post(f"/agents/{department}/evaluate-inline",
                               json={"case": case, "transcript": transcript, "thread_id": thread_id})
        except httpx.TimeoutException as e:
            raise AgentUnavailable("timeout", f"no answer within {AGENT_TIMEOUT_S:.0f} s") from e
        except httpx.HTTPError as e:
            raise AgentUnavailable("unreachable", type(e).__name__) from e
        if r.status_code != 200:
            raise AgentUnavailable("http_error", f"HTTP {r.status_code}: {r.text[:120]}")
        try:
            return r.json()
        except ValueError as e:
            raise InvalidAgentOutput("response was not JSON") from e


class LegacyThrowawayCaseClient:
    """TEMPORARY. For a Track C that does not have the stateless endpoint yet: writes a throwaway case row straight into
    Track C's SQLite file (TRACKC_DB_PATH), calls the existing POST /agents/{dept}/evaluate, then deletes the throwaway
    rows. Limitations: it couples this service to Track C's database layout, needs a shared volume, and the agent cannot see
    our transcript (Track C reads its own messages table). Remove it once integration/trackc-owner.patch is merged."""

    def __init__(self, base_url: str = TRACKC_URL, db_path: str = TRACKC_DB_PATH, timeout: float = AGENT_TIMEOUT_S,
                 transport: httpx.BaseTransport | None = None):
        if not db_path:
            raise ValueError("TRACKC_DB_PATH is required for TRACKC_MODE=legacy")
        self.db_path = db_path
        self.http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(timeout, connect=5), transport=transport)

    def evaluate(self, department: str, case: dict, transcript: list[dict], thread_id: str) -> dict:
        tmp_id = f"tmp-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO cases (id, category, ward, lat, lng, accuracy_m, description, status, hop_count, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'DISPUTE', 0, ?, ?)",
                (tmp_id, case["category"], case["ward"], case["lat"], case["lng"], case.get("accuracy_m"),
                 case.get("description", ""), now, now))
            conn.commit()
            try:
                r = self.http.post(f"/agents/{department}/evaluate", json={"case_id": tmp_id, "thread_id": tmp_id})
            except httpx.TimeoutException as e:
                raise AgentUnavailable("timeout", f"no answer within {AGENT_TIMEOUT_S:.0f} s") from e
            except httpx.HTTPError as e:
                raise AgentUnavailable("unreachable", type(e).__name__) from e
            if r.status_code != 200:
                raise AgentUnavailable("http_error", f"HTTP {r.status_code}: {r.text[:120]}")
            return r.json()
        finally:
            for table in ("messages", "query_log"):
                conn.execute(f"DELETE FROM {table} WHERE case_id = ?", (tmp_id,))
            conn.execute("DELETE FROM cases WHERE id = ?", (tmp_id,))
            conn.commit()
            conn.close()


def default_client() -> TrackCClient:
    return LegacyThrowawayCaseClient() if TRACKC_MODE == "legacy" else HttpTrackCClient()


# ----------------------------------------------------------------------------------------------- format conversion
def _case_payload(case: Case) -> dict:
    return {"id": case.id, "category": case.category.value, "ward": case.location.ward or shared_config.DEFAULT_WARD,
            "lat": case.location.lat, "lng": case.location.lng, "description": case.description}


def _transcript_payload(messages: list[AgentMessage]) -> list[dict]:
    """Our case thread in Track C's message shape, so the agent can see what the others said."""
    out = []
    for m in messages:
        if m.type not in TYPE_TO_TRACKC:
            continue
        out.append({
            "from": f"{m.from_agent.value}_agent", "to": "engine", "type": TYPE_TO_TRACKC[m.type],
            "target": f"{m.target_department.value}_agent" if m.target_department else None,
            "target_basis": m.target_basis, "rationale": m.reason,
            "evidence": [{"kind": e.kind, "source": e.source or "", "finding": e.summary or "", "ref": e.ref} for e in m.evidence],
        })
    return out


def _department(name: str | None, what: str) -> Department:
    name = (name or "").removesuffix("_agent")
    try:
        return Department(name)
    except ValueError as e:
        raise InvalidAgentOutput(f"{what} '{name}' is not a department") from e


def _check_basis(target: Department, basis: str | None, category: str, evidence_refs: dict[str, str], kinds_by_ref: dict[str, str]) -> str:
    """target_basis must be a real matrix rule for this category naming the target, or a cited handover record naming it."""
    if not basis:
        raise InvalidAgentOutput(f"a reference to {target.value} needs a target_basis")
    if basis.startswith("matrix_rule:"):
        rule = shared_config.rule(basis.split(":", 1)[1])
        if not rule or rule["category"] != category or target.value not in rule["candidates"]:
            raise InvalidAgentOutput(f"target_basis '{basis}' does not support {target.value} for category '{category}'")
        return basis
    if basis.startswith("handover_record:"):
        orig = basis.split(":", 1)[1]
        ref = evidence_refs.get(orig, orig)  # accept either Track C's original ref or one we already rewrote
        if kinds_by_ref.get(ref) != "handover_record":
            raise InvalidAgentOutput(f"target_basis '{basis}' does not cite a handover_record in the evidence")
        return f"handover_record:{ref}"
    raise InvalidAgentOutput("target_basis must be 'matrix_rule:<id>' or 'handover_record:<ref>'")


def to_agent_message(raw: dict, department: Department, case: Case, allow_sub_tasks: bool = True) -> AgentMessage:
    """Convert and validate one Track C message. Raises InvalidAgentOutput (or AgentUnavailable-free) on any problem."""
    if not isinstance(raw, dict):
        raise InvalidAgentOutput("response was not an object")
    if raw.get("type") == "error":
        reason = str(raw.get("error_reason") or "agent reported an error")
        raise InvalidAgentOutput(reason, kind="llm_error" if reason.startswith("llm_unavailable") else "invalid_output")
    frm = _department(raw.get("from"), "sender")
    if frm != department:
        raise InvalidAgentOutput(f"asked {department.value} but {frm.value} answered")
    t_type = raw.get("type")
    if t_type not in TYPE_FROM_TRACKC:
        raise InvalidAgentOutput(f"unknown message type '{t_type}'")
    mtype = TYPE_FROM_TRACKC[t_type]
    category = case.category.value

    evidence, ref_map, kinds_by_ref = [], {}, {}
    for e in raw.get("evidence") or []:
        kind, finding = e.get("kind"), e.get("finding") or ""
        if kind not in EVIDENCE_KINDS:
            raise InvalidAgentOutput(f"unknown evidence kind '{kind}'")
        new_ref = stable_ref(department.value, kind, finding)
        ref_map[e.get("ref", new_ref)] = new_ref
        kinds_by_ref[new_ref] = kind
        if all(x["ref"] != new_ref for x in evidence):  # the same finding cited twice is one piece of evidence
            evidence.append({"kind": kind, "ref": new_ref, "summary": finding, "source": e.get("source")})
    kinds = {e["kind"] for e in evidence}

    target = basis = None
    confidence = raw.get("confidence")
    if mtype == MessageType.accept:
        if "presence" not in kinds:
            raise InvalidAgentOutput("an accept needs presence evidence from the department's own registry")
    if t_type == "reject":
        target = _department(raw.get("target"), "target")
        if target == department:
            raise InvalidAgentOutput("a department cannot reject to itself")
        if target.value not in shared_config.candidates_for(category):
            raise InvalidAgentOutput(f"{target.value} is not a jurisdiction-matrix candidate for '{category}'")
        if not evidence:
            raise InvalidAgentOutput("a reject needs evidence")
        basis = _check_basis(target, raw.get("target_basis"), category, ref_map, kinds_by_ref)
        if kinds <= ABSENCE_ONLY_KINDS and confidence is not None:
            confidence = min(confidence, ABSENCE_ONLY_CAP)

    sub_tasks = []
    if t_type == "split":
        for s in raw.get("sub_tasks") or []:
            dept = _department(s.get("department"), "sub-task department")
            if dept == department:
                continue  # the accepting department's own part is the case itself
            if dept.value not in shared_config.candidates_for(category):
                raise InvalidAgentOutput(f"{dept.value} is not a jurisdiction-matrix candidate for '{category}'")
            sub_tasks.append({"department": dept, "task": s.get("task") or "Handle the remaining part of the complaint",
                              "target_basis": _check_basis(dept, s.get("target_basis"), category, ref_map, kinds_by_ref),
                              "rationale": s.get("rationale")})
        if not sub_tasks:
            raise InvalidAgentOutput("a split must propose a part for at least one other department")
    if sub_tasks and not allow_sub_tasks:
        raise InvalidAgentOutput("a sub-task answer cannot propose further sub-tasks")

    try:
        return AgentMessage(
            from_agent=department, type=mtype, target_department=target, target_basis=basis,
            reason=(raw.get("rationale") or "").strip() or f"{mtype.value} by {department.value}",
            evidence=evidence, confidence=confidence, sub_tasks=sub_tasks,
            missing=list(raw.get("missing") or []), model_backend=raw.get("model_backend"),
        )
    except ValidationError as e:
        raise InvalidAgentOutput(f"does not match the message contract: {e.errors()[0]['msg']}") from e


def fallback_message(department: Department, kind: str, detail: str) -> AgentMessage:
    """Safe answer when the agent gave nothing usable: hand the case to a human instead of guessing or crashing."""
    return AgentMessage(
        from_agent=department, type=MessageType.escalate,
        reason=f"Department agent unavailable ({kind}): {detail}"[:400], model_backend=f"fallback:{kind}",
    )


# ------------------------------------------------------------------------------------------------- the interface
def call_department_agent(
    department: Department | str,
    case: Case,
    transcript: list[AgentMessage] | None = None,
    sub_task: SubTask | None = None,
    client: TrackCClient | None = None,
) -> AgentMessage:
    """Ask `department`'s agent about `case`. Always returns a valid AgentMessage; never raises for agent problems.
    With `sub_task` the agent answers that proposed sub-task (no further sub-tasks allowed)."""
    dept = Department(department)
    thread = f"{case.id}:{sub_task.id}" if sub_task else case.id
    try:
        raw = (client or default_client()).evaluate(dept.value, _case_payload(case), _transcript_payload(transcript or []), thread)
        return to_agent_message(raw, dept, case, allow_sub_tasks=sub_task is None)
    except AgentUnavailable as e:
        return fallback_message(dept, e.kind, e.detail)
    except InvalidAgentOutput as e:
        return fallback_message(dept, e.kind, e.detail)
    except Exception as e:  # noqa: BLE001 -- a misbehaving agent must never crash the engine
        return fallback_message(dept, "invalid_output", f"unexpected {type(e).__name__}")
