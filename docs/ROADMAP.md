# Roadmap and verification gates

The capability-by-capability baseline is in
[`PRODUCTION_READINESS_AUDIT.md`](PRODUCTION_READINESS_AUDIT.md). This priority
order separates repository work from device/account qualification; CI success
does not mark a physical Mac/Pi or public release as qualified.

## Current priority order (2026-11-11)

### P0 — Protect and qualify the baseline
- [x] Existing branch has queue fencing, bounded retries, private artifact checks and rollback tag.
- [x] Python 3.11–3.13 CI plus Godot, FFmpeg and hosted-macOS synthetic media jobs pass at audited HEAD.
- [ ] Run isolated backup/restore and rollback qualification over representative queue, media and review data.
- [ ] Keep a written distinction between synthetic CI, mocks, and real-device results.

### P1 — Prove one real Arabic episode
- [ ] Render the existing Arabic colors pilot on the owner's Mac with approved original narration.
- [ ] Listen to and inspect the exact SHA-bound video; record owner notes and decision.
- [ ] Qualify same-revision Mac→Pi transfer and backup/restore on real devices.
- [ ] Separately authorize and execute one YouTube PRIVATE pilot; owner reviews the exact private draft.

### P2 — Evidence-backed Studio Director
- [x] Local private ledger persists unique proposals, caller-supplied evidence references, alternatives and immutable accept/reject/defer rationale.
- [x] Bounded, optional zero-paid AI proposal/review path can enqueue only an internally approved script draft; ordinary actor labels cannot accept work.
- [x] Record caller-supplied evidence provenance and byte hashes separately from source authenticity or factual verification.
- [ ] Add authenticated authority, verified research-source adapters, transparent cost bounds and model-assisted recommendation/decision evaluation.
- [ ] Keep decisions explainable, auditable and bounded by current worker allowlists and zero-paid defaults.

### P3 — Specialist agent teams
- [ ] Bind research, creative/character, educational/editorial, production and independent review to shared proposal/episode provenance.
- [ ] Preserve reviewer independence and existing bounded repair/retry limits.
- [ ] Evaluate real Arabic/English quality and safety with qualified human review where required.

### P4 — Measurement and learning
- [ ] Record authorized outcome measurements against exact published episode versions.
- [ ] Revisit old proposals only when new evidence is recorded; avoid repeated failed concepts without new evidence.
- [ ] Do not infer analytics that the owner has not authorized or supplied.

### P5 — Business and growth intelligence
- [ ] Add cost and revenue scenario analysis with assumptions clearly marked.
- [ ] Explore original educational products and licensing opportunities without automatic spending, sales or outreach.

P1 device and account steps require the owner's supervised operation and explicit
authorization where specified. Code can prepare those steps but cannot claim
they passed.

The Director synthetic pipeline is not an external research run or a real model
qualification. The Arabic episode on the owner's Mac remains Pending Physical
Qualification; a successful local/synthetic test does not establish script,
voice, visual, educational or publication readiness.

## Milestone 0 — Foundation (merged)
- [x] GitHub repository initial scaffold
- [x] Rig-first blueprint -> generation job list
- [x] Technical rig QA and tests
- [x] Constitution/rights/security boundaries
- [x] Confirm CI green and main branch merged

## Milestone 1 — Mac art pipeline
- [x] Read-only Mac ComfyUI API workflow and opt-in localhost node/model registry diagnostic, human-review profile skeleton, redacted private report (mock tested; no real Mac probe)
- [x] Unified Mac Doctor: reference integrity, pinned graph, localhost registry, Godot/FFmpeg versions, Ollama registration, private disk and strict no-GPU readiness result (CI mock tests)
- [x] Owner-invoked one-command Mac first-bunny art trial: strict preflight -> two reference-conditioned parts -> overlap/contact sheet -> one local AI reviewer, private journal and no retries (CI mocks only)
- [ ] Collect real Mac ComfyUI workflow and verify installed nodes/models plus previous Godot proofs (no model weights, rights docs or raw images in public repo)
- [x] Implement checksum-pinned localhost ComfyUI job submission and sequential part collection (requires a pre-approved transparency workflow on Mac); no model auto-download or paid inference
- [x] Strict anatomical placement/coverage/duplicate-art QA enforced for bunny blueprint, with **early abort before the next diffusion job** (offline synthetic tests)
- [x] Strict offline production graph audit: reference image conditioning + part text both feed sampler; sampler output passes through pinned alpha/matting stage to SaveImage, exact node-ID output collection (synthetic tests)
- [x] Two-part Mac art qualification command (body + right arm), alpha/placement early gating, neutral shoulder overlap and immutable contact-sheet/report (offline mock tests)
- [x] Five-panel partial arm rotation evidence and independent SHA-verified local visual evaluator with immutable PASS/REVISE/FAIL preliminary report (offline mock tests)
- [ ] Validate actual isolated layers, identity-conditioned generation and seamless rendered joint overlaps on Mac (live art unverified)
- [x] Layer-based GIF/contact-sheet evidence generator (deterministic)
- [x] Optional local AI vision reviewer: independent decision, evidence hashes, PASS/REVISE/FAIL gate (requires real Mac validation)
- [x] Bounded 1–3 attempt visual-REVISE loop with part-specific reuse, immutable attempts and strict output guardrails (offline tests)
- [ ] Validate repair effectiveness and review quality on real Mac models
- [x] Export a standalone Godot 4 rig project from manifest and JSON scene beats (native Mac render still pending)
- [ ] Benchmarks on actual Mac M3 Max and 48 GB shared memory

## Milestone 2 — Studio brain
- [x] Durable SQLite production-job state, audit journal, worker leases/fencing, crash recovery and local Studio Director CLI (offline integration tests)
- [ ] Persistent episode/script editorial schemas and linked revisions
- [x] Explicit per-role OpenAI-compatible multi-provider AI Chat router, env-only credentials, no paid/failover without opt-in (mock-tested)
- [x] Single-shot local worker for script_draft/editorial_review with persistent SQLite job acknowledgement (mock-tested)
- [x] Atomic draft-to-independent-review followup with private artifact SHA256, lineage verification and no copy of draft text in child queue payload (mock-tested)
- [ ] Independent structured child-development, factual, Arabic and English review decisions tied to one approved script revision
- [x] Authenticated TLS Pi coordinator with outbound-initiated Mac editorial client, role-limited leases, Pi private text vault and atomic review handoff (CI test only)
- [x] Pinned media recipes, Pi-to-Mac media-capability leasing and Mac-local at-most-one-start journal with fail-closed ambiguous recovery (mock render tests)
- [ ] Studio Director decision-making agent, deployed Pi↔Mac credentials/firewall, verified real Mac ComfyUI/Godot assets and cross-device idempotency hardening
- [ ] Independent bilingual editorial review committee
- [ ] Telegram private command bot with allowlisted IDs and emergency stop

## Milestone 3 — Full production
- [ ] Approved scene_spec.json -> Godot actions -> FFmpeg master
- [ ] Arabic/English voices, licensing/provenance and lip sync QA
- [ ] Visual identity and thumbnail production/review agents
- [ ] Coloring/parent activity generation and QR end card
- [ ] Provenance, archival verification and restore drill

## Milestone 4 — Distribution / feedback
- [ ] YouTube OAuth and PRIVATE uploads only, audience metadata and permission checks
- [ ] Owner approval gate for public release
- [ ] Check multilanguage-audio channel eligibility, else hold English master
- [ ] Adult-only Telegram community/moderation, unique topics per series
- [ ] Analytics of own channel + allowed public competitor research

## Release gate
No weekly series or full autonomy until one bilingual 3–4 min episode passes creative, language, pedagogic, rights, audiovisual and archive checks; public release must have owner approval.
