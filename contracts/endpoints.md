# Endpoint list (v0.2)

Base URL: `http://localhost:8000`. Interactive docs at `/docs`; machine-readable spec in `openapi.json`.
Schemas in `schemas/*.schema.json` are generated from `backend/app/models.py`; do not edit them by hand.

| Method | Path | Owner of caller | Purpose |
|---|---|---|---|
| POST | `/intake` | WhatsApp bot (F) | Citizen report in, `intake_response` out: `case_created` with the case, or `need_info` with a follow-up question to send back |
| POST | `/cases` | Intake agent | Create a case from `case_create`. If intake lacks info it returns `need_info` to the citizen instead of calling this |
| GET | `/cases` | Dashboard (F) | List cases. Filters: `status`, `ward`, `department`, `limit` |
| GET | `/cases/{id}` | F, C | One case |
| POST | `/cases/{id}/messages` | Department agents (C) | Post an `agent_message` (accept / reject / transfer / request_info / escalate) |
| GET | `/cases/{id}/messages` | F | Transcript for the dispute panel |
| GET | `/cases/{id}/audit` | F | Audit log |
| POST | `/cases/{id}/verify` | Field crew view (F) | After-photo plus GPS; returns `verify_result` |
| POST | `/cases/{id}/confirm` | WhatsApp buttons (F) | Citizen `resolved: true` closes, `false` reopens |
| GET | `/analytics/hotspots` | Dashboard (F) | Repeat disputes by ward and category |
| GET | `/health` | all | Liveness |

## Rules the engine enforces (live for /cases and /messages)

- `reject` and `transfer` need `target_department` and at least one `evidence` item (422 otherwise).
- Each `reject` or `transfer` is one hop. `hop_count` caps at 2; a third referral is recorded and the case becomes `escalated`.
- A department that rejected a case cannot be sent it again unless the message carries an evidence `ref` not seen earlier on that case (409).
- After a referral, only the department it was referred to may respond; the first message on a `new` case may come from any department (409 otherwise).
- After an `accept`, only the owner may post further messages (409 otherwise).
- Messages are rejected with 409 once a case is `in_progress` or later, `escalated` or `closed`.
- SLA deadline is set from severity: critical 4h, high 24h, medium 48h, low 72h. Past the deadline the case is flagged `sla.breached`; if still in the department or field phase it becomes `escalated`. The check runs on every read.
- Every state change and message writes an `audit_log` row.
- Only `/analytics/hotspots` is still a stub.

## Intake contract (for F)

- Send what the citizen gave: `text`, `voice_transcript` or `voice_url`, up to 3 `photo_urls`, and the WhatsApp location `pin`.
- Media URLs must be fetchable by the API without auth. WhatsApp media needs a token, so F downloads and re-hosts first.
- Intake is stateless. On `need_info`, send `need_info.question` to the citizen, keep their earlier text, photos and pin, and call `/intake` again with everything accumulated.
- Coordinates come only from the location pin. Without one, `need_info.missing` contains `location`.
- `need_info.missing` values: `details` (too vague), `photo` (blurry or irrelevant and the text is unclear), `location`, `retry` (model unavailable).
- Model timeout and fallback: any model call (Groq) slower than 15 s (`MODEL_TIMEOUT_S`), or that errors, hits quota or returns nothing usable, returns HTTP 200 with `result: need_info` and `need_info.missing = ["retry"]`, `question` = "Sorry, I could not process that just now. Please send it again in a minute." No case is created. F should send that question and keep the citizen's draft.
- 502 now means only that a media URL could not be fetched (F's re-hosting problem).
- Voice: send `voice_url` (WhatsApp OGG/Opus works). The model hears the audio and fills the case media transcript. Sending `voice_transcript` skips the audio step.
- 502 also covers a media URL that could not be fetched.

## Proof contract

- `POST /cases/{id}/verify` (field crew view): body `after_photo_url` (fetchable without auth), `lat`, `lng` of the crew's phone. Allowed when the case is `assigned`, `in_progress` or `reopened`; otherwise 409.
- Passes only if GPS is within 50 m of the case location (`VERIFY_RADIUS_M`) AND the vision check says same spot and resolved. The response gives `gps_ok`, `distance_m`, `vision_same_spot`, `vision_resolved`, a plain-language `reason` (show it to the crew and the citizen) and `passed`.
- Pass: status `awaiting_citizen`. Fail: status stays `in_progress`, the crew can resubmit. If GPS fails the vision check is skipped and the vision fields are `false`.
- The "before" photos are the photos from the original report. With none, same-spot is checked by GPS only.
- `POST /cases/{id}/confirm` (WhatsApp buttons): only valid when `awaiting_citizen`, else 409. `resolved: true` closes the case; `false` reopens it, keeping the owning department, and the crew can verify again.
- If the vision model is slow (over 15 s) or unavailable, `/verify` returns 200 with `retry: true`, `passed: false`, the case status unchanged and a reason telling the crew to resubmit. Nothing is decided. A GPS failure never needs the model, so it still reports normally. 502 means the after-photo URL could not be fetched.

## Case status flow

`need_info` -> `new` -> `in_dispute` -> `assigned` -> `in_progress` -> `pending_verification` -> `awaiting_citizen` -> `closed`
(`reopened` returns to `in_progress`; `escalated` on hop cap or SLA breach.)

## Open questions to lock with F and C

- Ward identifiers: free text; Track C uses ids like `W-12`, the only ward seeded.
- Auth: none during the hackathon.
- Field crew identity on `/verify`: not modelled yet.
