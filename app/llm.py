"""The model step (prompt.md 2.6 step 3): "The model gets the case, the prior
messages and the facts sheet, and must return exactly this structure."

Two backends:
  - gemini: real call to Gemini via google-genai, JSON-mode output.
  - fallback_rules: deterministic stub over the same facts sheet, used when
    GEMINI_API_KEY is unset or the live call fails/times out, so a hackathon
    demo never goes dark mid-pitch. Every AgentMessage records which backend
    actually decided it (message.model_backend) -- nothing is hidden.

In both cases this module ONLY chooses `type`/`cite_refs`/`target`/
`target_basis`/`sub_tasks`/`missing`/`rationale`. It never writes finding
text and never sets confidence -- validation.py owns both, per spec.
"""
from __future__ import annotations

import json
import logging

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.schemas import ModelDecision

logger = logging.getLogger("loci.llm")

SYSTEM_PROMPT = """You are a department agent inside a civic-complaint routing engine.
You represent exactly ONE department's registry. You must speak only for that
department's own data -- you may say "I found no X" but never assert what
another department's registry contains; cite a matrix rule instead.

You will be given:
- the case (category, ward, coordinates, description)
- a facts sheet: evidence your own registry's tools already produced (each
  with a ref, a kind, and a finding sentence already written in code), and
  the jurisdiction matrix rules for this category
- the prior transcript for this case/thread (what other departments said)

Return ONLY a single JSON object with exactly these fields, no prose outside it:
{
  "type": "accept" | "reject" | "split" | "need_info",
  "cite_refs": ["<ref>", ...],
  "target": "<department or null>",
  "target_basis": "matrix_rule:<id>" | "handover_record:<ref>" | null,
  "sub_tasks": [ { "department": "...", "task": "...", "cite_refs": ["..."], "target_basis": "...", "rationale": "..." } ],
  "missing": ["..."],
  "rationale": "One or two plain sentences."
}

Decision checklist -- follow this order, it resolves almost every case:
1. Does the facts sheet contain evidence with kind "presence" (one of YOUR
   OWN assets was actually found near the point)? If yes: that is strong
   evidence of your own standing.
     - If the facts sheet ALSO contains a "handover_record" evidence item,
       you only own PART of this complaint -- you MUST choose "split", never
       plain "accept". Your own sub_task cites the presence evidence; a
       second, proposed sub_task names the handover_record's receiving
       department with target_basis "handover_record:<ref>". Accepting
       outright would silently drop that department's part of the work.
     - Otherwise, choose "accept", citing the presence evidence.
   NEVER choose "reject" or "need_info" when you have presence evidence --
   a generic jurisdiction_rule=false finding does NOT override your own
   presence evidence; it only matters when you have no presence evidence.
2. No presence, but a handover_record was found (kind "handover_record")?
   Choose "reject" with that department as target and
   "handover_record:<ref>" as target_basis.
3. No presence, no handover_record, but the matrix lists another candidate
   department for this category (see candidate_departments_for_category)
   that you haven't already unsuccessfully tried? Choose "reject" naming
   that candidate, with "matrix_rule:<id>" as target_basis. Do this even if
   you are uncertain -- the engine automatically escalates to a human once
   every candidate has rejected, so a confident reject is always safe here.
4. Only if NO candidate department remains to try (you are the last resort)
   and you still found nothing: "need_info" is acceptable.
"need_info" asking for "exact_location" should otherwise be rare -- the
location you were given is exact; do not ask for a more precise location
just because nothing was found nearby, that's what step 3's reject is for.

Rules:
- Every ref in cite_refs (and in each sub_task's cite_refs) MUST be one of the
  refs given to you in the facts sheet. Never invent a ref.
- "accept" requires at least one cited ref whose kind is "presence".
- "reject" requires a target that appears in the facts sheet's matrix
  candidates for this category, is not yourself, and a target_basis that is
  either a real matrix_rule id from the facts sheet or a handover_record ref
  you cited.
- Never invent what another department's registry contains.
"""


def _client():
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai
    except ImportError:
        logger.warning("google-genai not installed; using fallback_rules backend")
        return None
    return genai.Client(api_key=GEMINI_API_KEY)


def _build_user_prompt(
    department: str, case: dict, facts: dict, transcript: list[dict], retry_feedback: str | None
) -> str:
    visible_evidence = [
        {"ref": e["ref"], "kind": e["kind"], "finding": e["finding"]} for e in facts["evidence"]
    ]
    payload = {
        "department": department,
        "case": {
            "id": case["id"], "category": case["category"], "ward": case["ward"],
            "description": case.get("description", ""), "accuracy_m": case.get("accuracy_m"),
        },
        "facts_sheet": {
            "evidence": visible_evidence,
            "matrix_rules_for_category": facts["matrix_rules"],
            "candidate_departments_for_category": facts["candidates_overall"],
        },
        "prior_transcript": transcript,
    }
    text = json.dumps(payload, indent=2)
    if retry_feedback:
        text += f"\n\nYour previous answer was rejected by validation: {retry_feedback}\nTry again, following the rules exactly."
    return text


def decide(
    department: str, case: dict, facts: dict, transcript: list[dict], retry_feedback: str | None = None
) -> tuple[dict, str]:
    client = _client()
    if client is None:
        return mock_decide(department, case, facts, transcript), "fallback_rules"

    try:
        from google.genai import types

        prompt = _build_user_prompt(department, case, facts, transcript, retry_feedback)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        raw = json.loads(resp.text)
        decision = ModelDecision(**raw).model_dump()
        return decision, "gemini"
    except Exception as exc:  # noqa: BLE001 -- any failure here must degrade, never crash the case
        logger.warning("Gemini call failed, falling back to deterministic rules: %s", exc)
        return mock_decide(department, case, facts, transcript), "fallback_rules"


def mock_decide(department: str, case: dict, facts: dict, transcript: list[dict]) -> dict:
    """Deterministic policy over the facts sheet. Used offline, and also a
    useful reference implementation for what a correct model answer looks
    like for each evidence shape."""
    evidence = facts["evidence"]
    category = facts["category"]
    candidates_overall = [c for c in facts["candidates_overall"] if c != department]

    presence = [e for e in evidence if e["kind"] == "presence"]
    handovers = [e for e in evidence if e["kind"] == "handover_record"]
    absences = [e for e in evidence if e["kind"] == "absence"]
    jurisdiction = [e for e in evidence if e["kind"] == "jurisdiction_rule"]

    def rule_for_target(target: str) -> str | None:
        for r in facts["matrix_rules"]:
            if target in r["candidates"]:
                return r["id"]
        return None

    # Own presence evidence + a handover record pointing elsewhere for the
    # part we don't own -> split (own the part we have presence for).
    if presence and handovers:
        own_asset = presence[0]
        ho = handovers[0]
        other_dept = ho["_raw"]["found"][0]["receiving_department"]
        other_order = ho["_raw"]["found"][0]["order_ref"]
        return {
            "type": "split",
            "cite_refs": [e["ref"] for e in presence + handovers + absences],
            "target": None,
            "target_basis": None,
            "sub_tasks": [
                {
                    "department": department,
                    "task": f"Address own asset near the reported point ({own_asset['finding']})",
                    "cite_refs": [own_asset["ref"]],
                    "target_basis": None,
                    "rationale": "Own registry shows a present asset at the point.",
                },
                {
                    "department": other_dept,
                    "task": "Repair/inspect the remaining part of the complaint per handover record",
                    "cite_refs": [ho["ref"]],
                    "target_basis": f"handover_record:{ho['ref']}",
                    "rationale": f"Own handover record {order_ref_label(other_order)} names {other_dept}.",
                },
            ],
            "missing": [],
            "rationale": "Own asset present for part of the complaint; own handover record names the other owner for the rest.",
        }

    # Pure presence -> accept.
    if presence:
        return {
            "type": "accept",
            "cite_refs": [e["ref"] for e in presence],
            "target": None,
            "target_basis": None,
            "sub_tasks": [],
            "missing": [],
            "rationale": "Own registry shows the relevant asset present at the reported point.",
        }

    # No presence, but an own handover record names who the asset went to -> reject there.
    if handovers:
        ho = handovers[0]
        other_dept = ho["_raw"]["found"][0]["receiving_department"]
        return {
            "type": "reject",
            "cite_refs": [e["ref"] for e in absences + handovers],
            "target": other_dept,
            "target_basis": f"handover_record:{ho['ref']}",
            "sub_tasks": [],
            "missing": [],
            "rationale": "No own asset present; own handover record names the likely owner.",
        }

    # Absence only -> reject to the next matrix candidate (engine enforces
    # the "not already rejected_by without new evidence" rule). Only cite the
    # jurisdiction finding when it actually reinforces the rejection (i.e. it
    # came back false) -- citing a "yes I am in jurisdiction" finding
    # alongside a reject would be self-contradictory.
    if candidates_overall:
        target = candidates_overall[0]
        rule_id = rule_for_target(target)
        reinforcing_jurisdiction = [e for e in jurisdiction if e["_raw"].get("in_jurisdiction") is False]
        return {
            "type": "reject",
            "cite_refs": [e["ref"] for e in absences + reinforcing_jurisdiction],
            "target": target,
            "target_basis": f"matrix_rule:{rule_id}" if rule_id else None,
            "sub_tasks": [],
            "missing": [],
            "rationale": "No own asset present; matrix suggests another department as the likely owner.",
        }

    # No candidates left to try and nothing found -- ask for a human/citizen check.
    return {
        "type": "need_info",
        "cite_refs": [e["ref"] for e in absences],
        "target": None,
        "target_basis": None,
        "sub_tasks": [],
        "missing": ["exact_location"],
        "rationale": "No own asset found and no further matrix candidate to try.",
    }


def order_ref_label(order_ref: str) -> str:
    return f"({order_ref})" if order_ref else ""
