"""Contract models. Single source of truth for /contracts JSON schemas and the OpenAPI doc."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Department(str, Enum):
    corporation = "corporation"
    water_board = "water_board"
    electricity = "electricity"
    highways = "highways"


class Category(str, Enum):
    """Canonical categories. These are Track C's names; contracts/jurisdiction_matrix.json is keyed by them."""
    pothole = "pothole"
    waterlogging = "waterlogging"  # water standing on a road: rain, drain overflow or a burst main
    drain_block = "drain_block"  # a blocked or choked drain
    garbage = "garbage"
    streetlight = "streetlight"
    water_leak = "water_leak"  # a leaking pipe or valve
    other = "other"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class CaseStatus(str, Enum):
    need_info = "need_info"  # intake could not form a valid case
    new = "new"
    in_dispute = "in_dispute"  # departments are referring the case among themselves
    assigned = "assigned"  # a department accepted ownership
    in_progress = "in_progress"  # field crew working
    pending_verification = "pending_verification"  # after-photo submitted
    awaiting_citizen = "awaiting_citizen"  # verified, waiting for citizen confirm
    closed = "closed"
    reopened = "reopened"
    escalated = "escalated"  # hop cap hit or SLA breached


class Channel(str, Enum):
    whatsapp = "whatsapp"
    app = "app"


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    address: str | None = None
    ward: str | None = None


class MediaItem(BaseModel):
    kind: str = Field(pattern="^(photo|voice|video)$")
    url: str
    transcript: str | None = Field(default=None, description="Speech-to-text for voice notes")


class SLA(BaseModel):
    due_at: datetime
    breached: bool = False


class Case(BaseModel):
    id: str
    status: CaseStatus
    category: Category
    severity: Severity
    description: str
    location: Location
    media: list[MediaItem] = []
    channel: Channel = Channel.whatsapp
    citizen_ref: str = Field(description="Opaque citizen id (hashed WhatsApp number)")
    owner_department: Department | None = None
    hop_count: int = Field(default=0, ge=0, le=2, description="Referrals so far; cap is 2, then escalate")
    rejected_by: list[Department] = Field(default=[], description="Departments that rejected; need new evidence to re-send")
    sla: SLA
    created_at: datetime
    updated_at: datetime


class CaseCreate(BaseModel):
    """Output of the intake agent. If info is missing the agent returns need_info instead of calling this."""
    category: Category
    severity: Severity
    description: str = Field(min_length=3)
    location: Location
    media: list[MediaItem] = []
    channel: Channel = Channel.whatsapp
    citizen_ref: str


class NeedInfo(BaseModel):
    status: CaseStatus = CaseStatus.need_info
    missing: list[str] = Field(description="e.g. ['location', 'photo']")
    question: str = Field(description="Follow-up question to send the citizen")


class MessageType(str, Enum):
    accept = "accept"
    reject = "reject"  # must name target_department and evidence
    transfer = "transfer"  # refer to another department; counts as a hop
    request_info = "request_info"
    escalate = "escalate"


class Evidence(BaseModel):
    kind: str = Field(pattern="^(registry|photo|boundary|history|note)$")
    ref: str = Field(description="Registry record id, media url, or short note")
    summary: str | None = None


class AgentMessage(BaseModel):
    id: str | None = None
    case_id: str | None = None
    from_agent: Department
    type: MessageType
    target_department: Department | None = None
    reason: str = Field(min_length=3)
    evidence: list[Evidence] = []
    created_at: datetime | None = None

    @model_validator(mode="after")
    def reject_and_transfer_need_target_and_evidence(self):
        if self.type in (MessageType.reject, MessageType.transfer):
            if self.target_department is None:
                raise ValueError(f"{self.type.value} requires target_department")
            if not self.evidence:
                raise ValueError(f"{self.type.value} requires at least one evidence item")
            if self.target_department == self.from_agent:
                raise ValueError("target_department must differ from from_agent")
        return self


class AuditEntry(BaseModel):
    id: str
    case_id: str
    actor: str = Field(description="intake | engine | <department> | field_crew | citizen")
    action: str
    detail: dict = {}
    at: datetime


class VerifyRequest(BaseModel):
    after_photo_url: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class VerifyResult(BaseModel):
    case_id: str
    gps_ok: bool
    distance_m: float
    vision_same_spot: bool
    vision_resolved: bool
    reason: str
    passed: bool
    status: CaseStatus
    retry: bool = Field(default=False, description="true when the vision model was unavailable or too slow; nothing was decided, resubmit")


class ConfirmRequest(BaseModel):
    resolved: bool = Field(description="true closes the case, false reopens it")
    comment: str | None = None


class Hotspot(BaseModel):
    ward: str
    category: Category
    case_count: int
    dispute_count: int = Field(description="Cases that were referred between departments")
    reopen_count: int


class HotspotResponse(BaseModel):
    hotspots: list[Hotspot]


class IntakeRequest(BaseModel):
    """Everything collected so far for one report. WhatsApp is stateless here: the caller (F) resends the
    accumulated text, photos and location pin on every call until intake returns a case."""
    citizen_ref: str
    channel: Channel = Channel.whatsapp
    text: str | None = None
    voice_transcript: str | None = Field(default=None, description="Optional. If omitted, intake sends the voice note audio to the model, which transcribes it")
    voice_url: str | None = Field(default=None, description="Voice note URL (OGG/Opus from WhatsApp is fine); must be fetchable without auth")
    photo_urls: list[str] = Field(default=[], max_length=3, description="Publicly fetchable image URLs hosted by the caller")
    location: Location | None = Field(default=None, description="WhatsApp location pin; intake never guesses coordinates")


class IntakeResponse(BaseModel):
    result: str = Field(pattern="^(case_created|need_info)$")
    case: Case | None = None
    need_info: NeedInfo | None = None
