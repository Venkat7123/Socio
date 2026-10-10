"""HTTP layer over the case engine. Only /analytics/hotspots is still a stub."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from . import db, engine
from .intake import IntakeAgent
from .llm import RETRY_MESSAGE, MediaFetchError, ModelUnavailable
from .verification import VerificationAgent
from .models import (
    AgentMessage, AuditEntry, Case, CaseCreate, CaseStatus, Category, ConfirmRequest,
    Department, Hotspot, HotspotResponse, IntakeRequest, IntakeResponse,
    NeedInfo, SubTask, VerifyRequest, VerifyResult,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="Civic Case Engine API",
    version="0.2.0",
    description="Track B core API. Cases, intake, dispute messages, audit, verify and confirm are real; analytics is still a stub. See /contracts.",
    lifespan=lifespan,
)


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


@app.exception_handler(engine.EngineError)
async def engine_error_handler(_: Request, exc: engine.EngineError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

_agent: IntakeAgent | None = None


def get_intake_agent() -> IntakeAgent:
    global _agent
    if _agent is None:
        _agent = IntakeAgent()
    return _agent


@app.post("/intake", response_model=IntakeResponse, tags=["intake"])
def intake(body: IntakeRequest, conn=Depends(get_conn), agent: IntakeAgent = Depends(get_intake_agent)):
    """Turn a citizen report into a case, or return need_info with a follow-up question.
    Stateless: resend all text, photos and the location pin collected so far on every call."""
    try:
        result = agent.process(body)
    except ModelUnavailable:
        # Model slow, down or out of quota: ask the citizen to resend instead of hanging or failing.
        return IntakeResponse(result="need_info", need_info=NeedInfo(missing=["retry"], question=RETRY_MESSAGE))
    except MediaFetchError as e:
        return JSONResponse(status_code=502, content={"detail": f"Intake unavailable: {e}"})
    if isinstance(result, NeedInfo):
        return IntakeResponse(result="need_info", need_info=result)
    return IntakeResponse(result="case_created", case=engine.create_case(conn, result))


@app.post("/cases", response_model=Case, status_code=201, tags=["cases"])
def create_case(body: CaseCreate, conn=Depends(get_conn)):
    """Create a case from the intake agent's output. SLA deadline is set from severity."""
    return engine.create_case(conn, body)


@app.get("/cases", response_model=list[Case], tags=["cases"])
def list_cases(
    status: CaseStatus | None = None,
    ward: str | None = None,
    department: Department | None = None,
    limit: int = Query(50, ge=1, le=200),
    conn=Depends(get_conn),
):
    return engine.list_cases(conn, status=status, ward=ward, department=department, limit=limit)


@app.get("/cases/{case_id}", response_model=Case, tags=["cases"])
def get_case(case_id: str, conn=Depends(get_conn)):
    return engine.get_case(conn, case_id)


@app.post("/cases/{case_id}/messages", response_model=AgentMessage, status_code=201, tags=["dispute"])
def post_message(case_id: str, body: AgentMessage, conn=Depends(get_conn)):
    """Department agent posts accept / reject / transfer / request_info / escalate. Protocol violations return 409."""
    return engine.post_message(conn, case_id, body)


@app.get("/cases/{case_id}/messages", response_model=list[AgentMessage], tags=["dispute"])
def list_messages(case_id: str, include_sub_tasks: bool = True, conn=Depends(get_conn)):
    """The dispute transcript. Sub-task messages carry `sub_task_id`; pass include_sub_tasks=false for the case thread only."""
    return engine.list_messages(conn, case_id, include_sub_tasks=include_sub_tasks)


@app.get("/cases/{case_id}/sub_tasks", response_model=list[SubTask], tags=["dispute"])
def list_sub_tasks(case_id: str, conn=Depends(get_conn)):
    engine.get_case(conn, case_id)  # 404 for an unknown case
    return engine.list_sub_tasks(conn, case_id)


@app.post("/cases/{case_id}/sub_tasks/{sub_task_id}/messages", response_model=AgentMessage, status_code=201, tags=["dispute"])
def post_sub_task_message(case_id: str, sub_task_id: str, body: AgentMessage, conn=Depends(get_conn)):
    """The target department answers a proposed sub-task: accept assigns it; anything else leaves it for a human."""
    return engine.post_sub_task_message(conn, case_id, sub_task_id, body)


@app.get("/cases/{case_id}/audit", response_model=list[AuditEntry], tags=["cases"])
def get_audit(case_id: str, conn=Depends(get_conn)):
    return engine.list_audit(conn, case_id)


_verifier: VerificationAgent | None = None


def get_verification_agent() -> VerificationAgent:
    global _verifier
    if _verifier is None:
        _verifier = VerificationAgent()
    return _verifier


@app.post("/cases/{case_id}/verify", response_model=VerifyResult, tags=["proof"])
def verify_case(case_id: str, body: VerifyRequest, conn=Depends(get_conn),
                agent: VerificationAgent = Depends(get_verification_agent)):
    """Field crew submits an after-photo plus GPS. Passes only if GPS is within the radius AND the vision check says
    same spot and resolved. A pass moves the case to awaiting_citizen; a fail leaves it in_progress."""
    try:
        return engine.verify_case(conn, case_id, body, agent)
    except MediaFetchError as e:
        return JSONResponse(status_code=502, content={"detail": f"Verification unavailable: {e}"})


@app.post("/cases/{case_id}/confirm", response_model=Case, tags=["proof"])
def confirm_case(case_id: str, body: ConfirmRequest, conn=Depends(get_conn)):
    """Citizen confirms (closes) or reopens a verified case."""
    return engine.confirm_case(conn, case_id, body)


@app.get("/analytics/hotspots", response_model=HotspotResponse, tags=["analytics"])
def hotspots(ward: str | None = None):
    return HotspotResponse(hotspots=[
        Hotspot(ward="W-12", category=Category.water_leak, case_count=9, dispute_count=5, reopen_count=2),
        Hotspot(ward="W-7", category=Category.pothole, case_count=6, dispute_count=1, reopen_count=0),
    ])


@app.get("/health", tags=["meta"])
def health():
    return {"ok": True}
