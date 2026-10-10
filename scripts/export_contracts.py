"""Regenerate /contracts from the Pydantic models and the FastAPI app. Run from repo root:
    python scripts/export_contracts.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402
from app.models import AgentMessage, AuditEntry, Case, CaseCreate, ConfirmRequest, IntakeRequest, IntakeResponse, NeedInfo, SubTask, VerifyRequest, VerifyResult  # noqa: E402

OUT = ROOT / "contracts"
SCHEMAS = {
    "case": Case,
    "case_create": CaseCreate,
    "need_info": NeedInfo,
    "intake_request": IntakeRequest,
    "intake_response": IntakeResponse,
    "agent_message": AgentMessage,
    "sub_task": SubTask,
    "audit_entry": AuditEntry,
    "verify_request": VerifyRequest,
    "verify_result": VerifyResult,
    "confirm_request": ConfirmRequest,
}

(OUT / "schemas").mkdir(parents=True, exist_ok=True)
for name, model in SCHEMAS.items():
    (OUT / "schemas" / f"{name}.schema.json").write_text(json.dumps(model.model_json_schema(), indent=2) + "\n")
(OUT / "openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"Wrote {len(SCHEMAS)} schemas and openapi.json to {OUT}")
