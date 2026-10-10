"""Pydantic models for the API surface and the internal agent message contract.

The agent message shape follows prompt.md section 2.6 "Agent message (updated
contract)" exactly: type, cite_refs, target, target_basis, evidence[], confidence,
sub_tasks[], missing[], rationale.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

EvidenceKind = Literal["presence", "absence", "handover_record", "jurisdiction_rule", "history"]
MessageType = Literal["accept", "reject", "split", "need_info", "error"]
SubTaskStatus = Literal["PROPOSED", "ASSIGNED", "NEEDS_INFO", "ERROR", "ESCALATED", "SPLIT"]
CaseStatus = Literal[
    "ROUTED", "DISPUTE", "ASSIGNED", "NEEDS_INFO", "ESCALATED", "ERROR", "SPLIT", "DUPLICATE_LINKED"
]


class CaseCreate(BaseModel):
    category: str
    ward: str = "W-12"
    lat: Optional[float] = None
    lng: Optional[float] = None
    description: str = ""
    accuracy_m: Optional[float] = None
    # Convenience for demo/testing: "P1".."P4" resolves to the seeded
    # scenario coordinates in app/data/seed_points.json instead of lat/lng.
    point_label: Optional[str] = None
    reported_by: Optional[str] = None


class CaseInfoReply(BaseModel):
    """Citizen's reply to a need_info request."""
    exact_location: Optional[dict] = None
    answers: dict = Field(default_factory=dict)


class Evidence(BaseModel):
    kind: EvidenceKind
    source: str
    finding: str
    ref: str


class SubTaskIn(BaseModel):
    department: str
    task: str
    cite_refs: list[str] = Field(default_factory=list)
    target_basis: Optional[str] = None
    rationale: Optional[str] = None


ModelDecisionType = Literal["accept", "reject", "split", "need_info"]


class ModelDecision(BaseModel):
    """Raw shape the LLM (or fallback stub) must return -- section 2.6 step 3.

    "error" is deliberately excluded: per spec, `error` is something the
    *pipeline* produces on model/validation failure, never something the
    model is asked to choose (2.6 step 5: never return need_info for a model
    failure either -- that would wrongly make the engine ask the citizen).
    """
    type: ModelDecisionType
    cite_refs: list[str] = Field(default_factory=list)
    target: Optional[str] = None
    target_basis: Optional[str] = None
    sub_tasks: list[SubTaskIn] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    rationale: str = ""


class SubTaskOut(BaseModel):
    id: str
    department: str
    task: str
    status: SubTaskStatus
    depends_on: Optional[str] = None
    target_basis: Optional[str] = None
    rationale: Optional[str] = None
    hop_count: int = 0


class AgentMessage(BaseModel):
    case_id: str
    thread_id: str
    from_: str = Field(alias="from")
    to: str
    type: MessageType
    evidence: list[Evidence] = Field(default_factory=list)
    target: Optional[str] = None
    target_basis: Optional[str] = None
    # Raw proposals as emitted by the agent (department/task/cite_refs/
    # target_basis/rationale) -- NOT yet assigned ids/status. The engine
    # resolves those into real sub_tasks rows (see app/engine.py); GET
    # /cases/{id}.sub_tasks is the authoritative, stateful view.
    sub_tasks: list[dict] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    rationale: str = ""
    model_backend: Optional[str] = None
    error_reason: Optional[str] = None

    model_config = {"populate_by_name": True}


class CaseOut(BaseModel):
    id: str
    category: str
    ward: str
    lat: float
    lng: float
    accuracy_m: Optional[float]
    description: str
    point_label: Optional[str]
    status: CaseStatus
    owner_department: Optional[str]
    linked_case_id: Optional[str] = None
    hop_count: int
    escalation_reason: Optional[str]
    needs_info_fields: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    transcript: list[dict] = Field(default_factory=list)
    sub_tasks: list[SubTaskOut] = Field(default_factory=list)
    adjudications: list[dict] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    case_id: str
    thread_id: str = "root"
