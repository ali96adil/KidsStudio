# Production Intelligence — Safe Integration Register

Status: OPT-IN TEST/QUALIFICATION MODULES / NO LIVE RUNTIME CHANGES
Branch: feature/production-intelligence-safe-integration
Date: 2026-11-04

## Baseline and scope
- Preserve main, existing job contracts, local SQLite schema, pinned media recipes, worker fencing and journals, approved assets, and owner-only public-release approval.
- The README describes early R&D; remote transport and media worker are development prototypes, not verified live deployments.
- Existing bounded character repair and draft→review already implement portions of self-correction. Extend these rather than replace them.
- No API spend, model downloads, Pi/Mac deployment, uploads, or publishing from this planning change.

## Proposed workstreams (all opt-in, separately gated)
1. Evals: deterministic fixtures first; 10-run statistical evaluation only for selected nondeterministic tasks, with costs and seeds recorded.
2. Review loops: independent review and exact artifact SHA; bounded retries and explicit terminal state; reuse existing character cycle.
3. Scoped parallelism: separate independent editorial/media jobs only after queue leases and idempotency are verified; no competing writes to approved assets.
4. Handoff: machine-readable snapshot of branch, commit, queue state, pending jobs, decisions and blockers; exclude secrets/private media.
5. Agent instructions: lightweight AGENTS.md and CLAUDE.md pointing to authoritative docs, not duplicate logic.
6. Provider optimization: benchmark quality, latency, cost and privacy; opt-in only, no silent paid fallback.
7. Diagnosis-first bug workflow and retrospective lessons; tests remain source of truth.

## Rollout gates
G0 inventory current workflows, tests, status, dependencies and pending work; capture exact baseline commit.
G1 documentation and read-only eval harness with synthetic fixtures; prove no production side effects.
G2 run CI and regression tests; compare against baseline.
G3 opt-in pilot on one synthetic episode with separate artifacts; no external publishing.
G4 Mac/Pi live qualification with operator present; backup/restore test; reconcile uncertain journal entries.
G5 enable only after documented review and owner authorization.

## Acceptance criteria
- Existing tests remain passing; new tests cover failure paths, retries, duplicate jobs, cancellation, secret redaction and provenance.
- No modifications to main until review and verified CI.
- Every proposed change has a test, rollback procedure and audit entry.
- Human approval remains required for public release; private upload requires separately configured credentials and explicit deployment.
- Do not treat CI mock tests as live Mac/Pi verification.

## Decision log
- 2026-11-04: User requested safe integration and comprehensive logging.
- 2026-11-04: Created isolated feature branch; planning document only, no production execution.
- Existing queue and bounded repair are the integration points, not replacement targets.

## Open checks
- Capture main HEAD SHA and current CI run results.
- Inventory full repo tree and actual implementation coverage.
- Confirm Mac/Pi deployed versions and data backup before live work.
- Identify exact eval fixtures and metrics with educational, Arabic/English, visual and audio reviewers.

## Craft Anything and FilmCraft optional pilots (2026-11-07)

- **Pilot 38:** `kidsstudio/craft_ui_evidence.py` accepts privately captured screenshots of the **KidsStudio-owned** dashboard at 375/768/1280 CSS-width labels; checks current-file SHA256 and limited PNG dimensions, and never runs a coding agent, Craft CLI or MCP. Manual layout review remains mandatory.
- **Pilot 39:** `kidsstudio/filmcraft_export_check.py` verifies a private candidate MP4 SHA256 before/after an operator-requested local ffprobe, checking H.264/AAC, 1280×720, frame rate and stereo 48 kHz audio. This does not run FilmCraft or prove the video came from it. Manual Arabic captions, sound and visual checks remain mandatory.
- Shared `kidsstudio/optional_tool_evidence.py` enforces private regular evidence files outside Git. Both pilots are additive, fail-closed and **read-only**, with no changes to the existing Godot/FFmpeg renderer, worker, queue, Pi handoff or YouTube publishing.
- See [CRAFT_FILMCRAFT_OPTIONAL_PILOTS.md](CRAFT_FILMCRAFT_OPTIONAL_PILOTS.md) for operator commands, test limitations and rollback. Real Mac/Pi and optional-tool qualification remain **NOT_RUN**.


## Visual comparison extensions — batches 40–42 (2026-11-07)

- `craft_ui_pixel_compare.py`: fully decode and compare **two sets** of three private hash-verified 375/768/1280 dashboard PNG screenshots; report per-viewport color and changed-pixel ratios, with no auto approval, screenshot output or Craft agent invocation.
- `filmcraft_baseline_compare.py`: independently hash and ffprobe two private delivery MP4s, confirm H.264/AAC technical requirements, matching nominal frame rates and <=0.10-second duration delta. This is **not** a full visual or audio comparison.
- `filmcraft_frame_compare.py`: after the technical check, use local ffmpeg to decode six in-memory 320×180 frames at three relative timeline positions; report frame differences, then rehash both files. This checks **samples only**, not complete quality or subtitles.
- No installation, remote tool, real alpha-tool execution, publication, queue mutation or transfer was performed. Source identity is unverified; physical Mac/Pi G4 remains NOT_RUN. Runbooks and thresholds are documented in `CRAFT_FILMCRAFT_OPTIONAL_PILOTS.md`.
