"""Drives a new case through the department agents. The engine stays the engine of record: every message the agents
produce is posted through engine.post_message / post_sub_task_message, so the state machine, the hop cap (2) and the
validation rules apply unchanged. This module only decides whom to ask next.

Flow: ask the first-contact department (shared routing seed); post its answer; if it rejected, ask the department it named;
if it accepted, answer any sub-tasks it proposed by asking their departments. If the engine refuses a message (409: for example
a department sending the case back without new evidence), the department that was blocked escalates the case, with the
transcript and the reason, so a human takes over. The engine's 409 rule itself is untouched.
"""
from typing import Callable

from . import engine, shared_config
from .department_agents import call_department_agent
from .engine import EngineError
from .models import AgentMessage, CaseStatus, Department, MessageType, RouteResponse, RouteStep, SubTaskStatus

MAX_STEPS = 12  # far above hop cap + 1; a safety bound, never reached in a healthy run

AgentCaller = Callable[..., AgentMessage]


def _summarize(messages: list[AgentMessage]) -> list[dict]:
    return [{"from": m.from_agent.value, "type": m.type.value,
             "target": m.target_department.value if m.target_department else None, "basis": m.target_basis,
             "evidence": [f"{e.kind}: {e.summary}" for e in m.evidence], "reason": m.reason,
             "model_backend": m.model_backend} for m in messages]


def _transcript_text(messages: list[AgentMessage]) -> str:
    lines = []
    for m in messages:
        arrow = f" -> {m.target_department.value}" if m.target_department else ""
        ev = f" [{m.evidence[0].kind}: {m.evidence[0].summary}]" if m.evidence else ""
        lines.append(f"{m.from_agent.value} {m.type.value}{arrow}{ev}")
    return "; ".join(lines)


def _step(msg: AgentMessage, sub_task_id: str | None = None, note: str | None = None) -> RouteStep:
    return RouteStep(department=msg.from_agent, sub_task_id=sub_task_id, type=msg.type, target_department=msg.target_department,
                     model_backend=msg.model_backend, confidence=msg.confidence, note=note)


def _escalate_blocked(conn, case_id: str, blocked: AgentMessage, error: EngineError, steps: list[RouteStep]) -> None:
    """The engine refused `blocked`. The department that sent it escalates, citing the reason and the transcript."""
    transcript = engine.list_messages(conn, case_id)
    reason = f"Escalated: the engine blocked {blocked.from_agent.value}'s {blocked.type.value}: {error.detail}. Transcript: {_transcript_text(transcript)}"
    engine.audit_event(conn, case_id, blocked.from_agent.value, "blocked_message",
                       {"blocked": blocked.type.value, "target": blocked.target_department.value if blocked.target_department else None,
                        "reason": error.detail, "transcript": _summarize(transcript)})
    esc = AgentMessage(from_agent=blocked.from_agent, type=MessageType.escalate, reason=reason[:1500],
                       model_backend="driver:escalate_on_block")
    try:
        engine.post_message(conn, case_id, esc)
    except EngineError:
        engine.escalate_case(conn, case_id, reason, actor="driver")  # the state machine still decides whether this is legal
    steps.append(_step(esc, note=f"blocked by engine: {error.detail}"))


def _answer_sub_tasks(conn, case_id: str, call: AgentCaller, steps: list[RouteStep]) -> None:
    for sub in engine.list_sub_tasks(conn, case_id):
        if sub.status != SubTaskStatus.proposed:
            continue
        case = engine.get_case(conn, case_id)
        msg = call(sub.department, case, engine.list_messages(conn, case_id), sub_task=sub)
        try:
            engine.post_sub_task_message(conn, case_id, sub.id, msg)
            steps.append(_step(msg, sub_task_id=sub.id))
        except EngineError as e:
            fb = AgentMessage(from_agent=sub.department, type=MessageType.escalate, model_backend="driver:escalate_on_block",
                              reason=f"Escalated: the engine refused {sub.department.value}'s answer to the sub-task: {e.detail}"[:400])
            engine.post_sub_task_message(conn, case_id, sub.id, fb)
            steps.append(_step(fb, sub_task_id=sub.id, note=f"blocked by engine: {e.detail}"))


def route_case(conn, case_id: str, call: AgentCaller = call_department_agent) -> RouteResponse:
    case = engine.get_case(conn, case_id)
    if case.status not in (CaseStatus.new, CaseStatus.reopened):
        raise EngineError(409, f"Case is {case.status.value}; only a new or reopened case can be routed")
    ward = case.location.ward or shared_config.DEFAULT_WARD
    first, _confidence = shared_config.first_contact(case.category.value, ward)
    steps: list[RouteStep] = []
    if first is None:
        engine.escalate_case(conn, case_id, f"No department is a candidate for '{case.category.value}' in {ward}: human triage", actor="driver")
        return RouteResponse(case=engine.get_case(conn, case_id), first_contact=None, steps=steps)

    current = Department(first)
    for _ in range(MAX_STEPS):
        case = engine.get_case(conn, case_id)
        msg = call(current, case, engine.list_messages(conn, case_id))
        try:
            engine.post_message(conn, case_id, msg)
        except EngineError as e:
            if e.status_code != 409:
                raise
            _escalate_blocked(conn, case_id, msg, e, steps)
            break
        steps.append(_step(msg))
        if msg.type == MessageType.accept:
            _answer_sub_tasks(conn, case_id, call, steps)
            break
        if msg.type in (MessageType.reject, MessageType.transfer):
            if engine.get_case(conn, case_id).status == CaseStatus.escalated:
                break  # the hop cap escalated it
            current = msg.target_department
            continue
        break  # request_info or escalate: a person has to act
    return RouteResponse(case=engine.get_case(conn, case_id), first_contact=Department(first), steps=steps)
