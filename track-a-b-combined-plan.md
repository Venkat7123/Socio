# Combined Plan: Track A (Input and Proof) + Track B (Core and Data)

Owner: Pranav. Assumes a 36-hour build. Scale phases down for 24 hours.
Track C (department network) is owned by a teammate. Track F (frontend) is owned by the frontend teammate.

Reconcile task names with the original Track A and B docs; this plan was rebuilt from the chat summary.

## Legend

- **[YOU]** you build it
- **[->F]** offload to the frontend teammate
- **[->C]** offload to the Track C teammate
- **[STRETCH]** first things to cut

---

## Phase 1 : Contracts and stubs (Track B only)

This is the unblocker. F and C are idle until it ships.

- [x] **[YOU]** Lock the case schema, agent message schema and endpoint list with everyone (hours 0-2)
- [x] **[YOU]** Commit JSON schemas and the endpoint list to `/contracts`
- [x] **[YOU]** Write the OpenAPI doc
- [x] **[YOU]** Ship stub endpoints returning valid sample JSON
- [ ] **[->C]** Write sample agent messages for S2, S3 and S4 so F can build the transcript panel
- [x] **[YOU]** Set up the database and project skeleton

**Gate:** F can call your stubs and C knows the message format. Do not start Track A until this is done.

---

## Phase 2 : Real engine

- [x] **[YOU]** Case state machine and SLA clock
- [x] **[YOU]** Message validation (a reject needs a target and evidence; no re-sending to a department that rejected without new evidence)
- [x] **[YOU]** Transfer cap of 2, then escalation
- [x] **[YOU]** Audit log and message log
- [x] **[YOU]** `POST /cases`, `GET /cases`, `POST /cases/{id}/messages` working for real
- [ ] **[->C]** Registry seeding for one ward and the test scenarios

**Gate:** a case can be created and moved through states with fake agent messages.

---

## Phase 3 (hours 14-24): Track A core

- [ ] **[->F]** WhatsApp plumbing (Cloud API or Twilio sandbox): webhook, receiving messages, sending replies, media download (voice notes arrive as OGG/Opus)
- [x] **[YOU]** Intake agent: voice, photo and text into a valid case JSON (category, severity, location)
- [x] **[YOU]** Intake edge cases: missing location (accept a WhatsApp location pin), vague text, blurry photo. Return `need_info` instead of garbage
- [ ] **[YOU]** Plug C's real agents into the engine dispute loop
- [ ] **[->F]** Citizen and field crew notifications (case status messages). WhatsApp allows free-form replies only within 24 hours of the citizen's last message; later updates need pre-approved templates

**Gate:** a voice note plus photo becomes a case, routed by real agents.

---

## Phase 4 (hours 24-30): Proof

- [x] **[YOU]** Verification agent: GPS within a radius plus a vision model answering "same spot, issue resolved" yes/no with a reason
- [x] **[YOU]** `POST /cases/{id}/verify` and `POST /cases/{id}/confirm`
- [ ] **[->F]** Citizen confirm/reopen as WhatsApp interactive reply buttons
- [ ] **[YOU]** Analytics query for `GET /analytics/hotspots` (F builds the view)

**Gate:** a bad after-photo is blocked, and a good one closes the case.

---

## Phase 5 (hours 30-36): Integration and demo

- [ ] **[YOU]** Run S1 to S7 end to end and fix engine bugs
- [ ] **[YOU]** Metrics from the test set
- [ ] **[YOU]** Dashboard backup recording (with F)
- [ ] **[STRETCH]** Duplicate check (geo radius plus category)
- [ ] **[STRETCH]** Adjudication logic (C's; the first thing C drops)

---

## Cut list (agree on this today)

Drop in this order if behind at hour 20:

1. Duplicate check
2. Hotspot analytics
3. Adjudicator and baseline comparison
4. Any second language

**Never cut:** the dispute protocol, intake, and verification. These are the differentiators.

## Scope limits

- WhatsApp only (citizen channel, per the architecture diagram)
- No web form unless WhatsApp fails
- One regional language for voice
- Verification stays simple: GPS radius plus a yes/no vision check with a reason

## Risks

- **Phase 1 is a hard deadline.** If stubs slip past hour 4, two teammates are idle and integration risk compounds.
- **Verification is built last, so it is the riskiest item.** Prototype it as a standalone script around hour 10 while waiting on integration, then wire it in.
- **You are the single point of failure.** Make sure one teammate knows the engine well enough to unblock themselves.
- **Offloads only work if teammates accept them.** Ask before hour 4, not after you are drowning.
