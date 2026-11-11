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

## Batch 72 — bounded AI proposal and independent review

- The optional `studio-director pilot` route uses the existing `ChatRouter` and
  existing `StudioQueue`; it permits only explicitly free loopback providers,
  disables failover, and requires different writer and reviewer providers.
- The model receives only caller-supplied evidence. No web/research tool is
  invoked. Evidence excerpts are SHA-256 bound to their stored bytes; this
  verifies byte integrity only, not source authenticity or factual accuracy.
  Unsupported/revision/block verdicts, unverified evidence, missing estimates,
  or effort above eight hours defer the idea without creating a queue task.
- Automatic internal acceptance is restricted to a reviewed `script_draft`
  and carries `studio_no_paid` plus a versioned policy tag. Local and remote
  workers enforce loopback/free provider filtering for that tag, regardless of
  their normal paid-provider configuration. No cost, publishing or external
  action is authorized. Manual actor strings can reject/defer only; they are
  never owner credentials.
- Proposal, assessment, decision, dispatch and terminal result digests are
  recorded locally. Trial request keys bind the original brief/language/
  evidence to prevent silently reusing a key with changed input. The result
  ledger stores status and digest, not result content.
- Synthetic end-to-end tests use a deterministic router double and queue
  completion; they do not call a real model or prove Arabic quality. External
  research and the owner's Arabic Mac episode remain NOT_RUN / Pending Physical
  Qualification. Roll back by reverting the Batch 72 commit; no existing queue
  state, media recipe, provider credentials or hardware deployment changes.

## Batch 66 — macOS test reproducibility and SQLite lifecycle (2026-11-08)

- Baseline/rollback point: local tag `codex-restore-20261108-batch65` at
  `b9ce3eed1e9d8f310d6c7fb3e357a9bc0a954eb1` before this batch.
- `scripts/run_tests.py` canonicalizes the **test-only** temporary root. This
  accommodates macOS's `/var` system alias without weakening any production
  symlink rejection or private-path policy.
- CI now runs Python 3.11, 3.12 and 3.13, compiles source/tests/scripts, and
  executes the complete unit suite on the hosted macOS job before media smokes.
- Episode notes, private video-review history and the Mac media journal now
  close every SQLite connection explicitly after commit/rollback. Regression
  tests track initialization, read and write connection lifecycles.
- Rollback is one revert of this batch or checkout of the tagged baseline. No
  queue schema, worker capability, episode state, media recipe, upload policy,
  credential, device service or publication gate changed.

## Batch 67 — keep supplied narration pinned through Mac encoding

- The colors pilot carries the original verified WAV SHA-256 into the mux.
  A regression replaces the WAV during picture encoding and verifies that
  the real mux gate rejects it before probing media or creating a final MP4.
- The full Linux unit suite and real FFmpeg colors smoke passed. The smoke
  uses synthetic audio and simulated Pi, YouTube PRIVATE and owner review.
- Rollback point: Batch 66 (`0bfba51875afba71dfe0552479b7f64a47d55880`).
  Revert the batch on the integration branch if needed. Physical Mac/Pi
  qualification, Arabic listening, real OAuth/upload and owner review are NOT_RUN.

## Batch 68 — validate both Mac destinations before render

- The Mac launcher validates private output and evidence directories together
  before rendering. Missing directories are created with owner-only access.
  Existing symlinks and unsafe directories are rejected without changing
  permissions or creating files through those paths.
- Rollback: revert this batch to Batch 67
  (`9a856f15d2525bd64b4b3bb6f34fc6a893600a1e`). Physical Mac/Pi remains NOT_RUN.

## Batch 69 — pin the actual mux output through launcher QA

- The mux reports the digest and length of its checked staging MP4. The
  launcher uses that digest for playback QA and the private evidence sidecar.
  Regressions exercise replacement after staging and after the renderer
  returns. A substituted file cannot obtain a new digest from the launcher.
- The Linux unit suite, Bash syntax, compile checks and real FFmpeg colors
  smoke passed. Rollback is a revert to Batch 68
  (`ca6310b9d22f03301da635293ea13429e61e4693`).

## Batch 70 — bind launcher evidence to the pre-render source revision

- The Mac launcher captures the clean Git commit from its preflight and
  compares it before rendering and during evidence collection. A different
  clean checkout cannot be substituted as the source of that sidecar.
- The standalone collector retains its existing interface and accepts an
  optional expected commit. Hosted macOS smoke checks the sidecar against the
  workflow checkout. Rollback is a revert to Batch 69
  (`e37d748b6be1edc03878764b8f243a96dec43470`).
