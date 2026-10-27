# Roadmap and verification gates

## Milestone 0 — Foundation (merged)
- [x] GitHub repository initial scaffold
- [x] Rig-first blueprint -> generation job list
- [x] Technical rig QA and tests
- [x] Constitution/rights/security boundaries
- [x] Confirm CI green and main branch merged

## Milestone 1 — Mac art pipeline
- [ ] Import asset metadata from local ComfyUI and previous Godot proofs (no model weights, rights docs or raw images in public repo)
- [x] Implement checksum-pinned localhost ComfyUI job submission and sequential part collection (requires a pre-approved transparency workflow on Mac); no model auto-download or paid inference
- [x] Strict anatomical placement/coverage/duplicate-art QA enforced for bunny blueprint, with **early abort before the next diffusion job** (offline synthetic tests)
- [x] Strict offline production graph audit: reference image conditioning + part text both feed sampler; sampler output passes through pinned alpha/matting stage to SaveImage, exact node-ID output collection (synthetic tests)
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
