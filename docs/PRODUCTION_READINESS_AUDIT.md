# Kids Studio production readiness audit

Audit baseline: `c749452a1c5aeeb9e8b7d443aa91ca254de1897b`
Branch: `feature/production-intelligence-safe-integration`
PR: #33, open Draft, not merged
Audit date: 2026-11-11

This audit distinguishes repository code and synthetic/CI evidence from
qualification on the owner's Mac, Pi, accounts, and production media. A passing
unit or CI run does not qualify real hardware, actual Arabic narration, artistic
quality, child-development suitability, rights, or public release.

## Capability matrix

| Capability | Implemented | Tested | Integrated | Production ready | Missing / qualification |
|---|---|---|---|---|---|
| Rig specification and technical QA | Yes: blueprint planning, geometry/alpha/part checks | Unit tests and synthetic assets | Connected to Character Factory and Godot export | No; technical checks do not judge artistic quality or originality | Real isolated character parts, identity consistency, motion seams, rights review |
| Character Factory and ComfyUI | Yes: pinned local workflow, reference conditioning, bounded part repair, provenance | Mock ComfyUI and reviewer tests | Local factory → rig QA → preview/review path | No; owner Mac workflow and local models are unqualified | Real two-part/full-rig run and independent human art review |
| Godot and FFmpeg rendering | Yes: rig exporter/player and original colors episode pipeline | Real synthetic-asset Godot and FFmpeg CI smokes | Render output feeds technical checks and private evidence flow | No; the user's Mac and production artwork/audio have not been qualified | Real Mac render; full-length original episode and human audiovisual review |
| Script worker and editorial review | Yes: single-shot allowlisted worker, provider routing, draft-to-review handoff | Mock providers, hash/provenance, and failure tests | Uses the durable queue and private artifact references | No; no qualified bilingual review panel or deployed worker | Independent Arabic/English, factual, pedagogic, child-safety and originality review on one script revision |
| Studio Brain queue and worker transport | Yes: local SQLite queue, idempotency, leases/fencing, bounded retries, TLS coordinator prototype | Unit and synthetic TLS integration tests | Supports text jobs and pinned media recipe jobs | No; no deployed Pi/Mac service or real cross-device operation | Device backups, clock qualification, credentials/firewall setup, real transfer and recovery drill |
| Studio Director and proposal decisions | Partial: private proposal ledger and explicit decision-to-queue handoff, plus queue-control CLI; no autonomous decision agent | Ledger/queue handoff unit-tested; no autonomous decision eval | Accepted proposals link to existing idempotent queue jobs; research and agent recommendation remain unintegrated | No | Verified research sources, authenticated decision authority, cost bounds, learning/outcomes and supervised Director agent |
| Episode lifecycle and independent review | Partial: read-only lifecycle projection, notes, review receipts/history and bounded repair | Unit tests and synthetic SHA-bound review pipeline | Review and owner-note flows connect to private draft evidence | No | End-to-end run on the exact rendered episode; make script/artifact review lineage visible as one lifecycle |
| Mac → Pi transfer | Yes: foreground sender and fixed receiver with SHA/size checks | Synthetic in-process receiver and hosted CI | Integrated in the simulated private chain | No; CI does not use the physical Pi or LAN | Matching revisions, host-key verification, live LAN transfer and restore evidence |
| YouTube PRIVATE and owner review | Yes: foreground PRIVATE-only resumable uploader, journal, post-upload review UI | Mock OAuth/YouTube plus synthetic end-to-end chain | Integrated in simulation after transfer; uploader is not auto-dispatched | No; no real OAuth/upload or owner viewing | Explicit owner-authorized PRIVATE pilot, current privacy verification, review of exact draft; public release remains owner-only |
| Research and audience intelligence | Not implemented as a system capability | None | No | No | Authorized source adapters, evidence provenance, dated findings and opportunity evaluation; no fabricated metrics |
| Analytics, learning and business intelligence | Not implemented as an integrated capability | Mechanical script evals and media checks only | No connection from published outcomes to future proposals | No | Authorized channel analytics, costs, assumptions, decision memory, product/licensing scenarios |
| Backup, archival and restore | Partial: archive verification job kind and documented requirements | Component-level checks only | Not yet demonstrated with a complete production archive | No | Isolated restore/rollback drill with verified queue, media, review records and snapshots |

## Architecture findings

- Keep the SQLite queue, worker fencing, private artifact stores, pinned media
  recipes, Character Factory, renderer and publication gate. They already cover
  useful execution and safety contracts.
- Add a thin Studio Director/intelligence layer over the existing queue. It
  should persist proposal evidence, alternatives, decision rationale and
  authority/cost constraints, then enqueue only accepted, typed work. Do not
  make the Director a second scheduler or give it arbitrary shell/network tools.
- Preserve an independent review role and bind its decision to exact script and
  media hashes. Production agents must not approve their own output.
- Keep real Mac/Pi, ComfyUI, Arabic listening, OAuth, YouTube, backup/restore,
  and public release in separate qualification states; synthetic success must
  never promote those states.
- Current evidence has a scope mismatch in older summary prose: tests and CI
  establish code behavior with synthetic assets and mocks, not a live studio
  deployment. The current CI matrix runs Python 3.11–3.13; repository-hosted
  Godot, FFmpeg and macOS jobs were successful for this baseline.

## Prioritized roadmap from this audit

1. **P0 — Protect and qualify the baseline:** retain branch/rollback points,
   run regression CI, verify DB/media restore in isolation, and keep hardware
   claims explicit. Repository checks are green; physical qualification is
   pending.
2. **P1 — Prove one real Arabic episode:** run the existing colors pilot on
   the owner Mac with original narration, listen/review the exact file, then
   qualify same-revision Pi transfer and a separately authorized PRIVATE
   upload/owner review. No new rendering system is needed.
3. **P2 — Add evidence-backed Studio Director decisions:** persist unique
   proposal IDs, sources, alternatives and rationale; require explicit
   decisions and bounds; make approved proposals create existing typed queue
   jobs with idempotency and audit linkage.
4. **P3 — Connect specialist teams:** research, character, education/editorial,
   media and independent QA roles consume the same proposal/episode records;
   use existing worker capabilities and bounded retries.
5. **P4 — Learn from outcomes:** record authorized measurements against exact
   episode versions and review decisions; allow old proposals to be re-evaluated
   when evidence changes. Never infer unavailable audience statistics.
6. **P5 — Add commercial analysis:** model production costs and potential
   educational products/licensing as explicit scenarios; prohibit financial
   transactions and external outreach without owner approval.

P1 requires supervised access to the owner's devices, voice/media and accounts;
software work can prepare and test those paths but cannot claim their success.

## Verification evidence and rollback

- Baseline branch HEAD: `c749452a1c5aeeb9e8b7d443aa91ca254de1897b`.
- Full local suite: `python scripts/run_tests.py` — 838 tests passed on Python
  3.12.14.
- GitHub checks for this exact commit: CI, Real Godot smoke, Real colors
  episode encoding smoke, and hosted macOS colors smoke all completed
  successfully on 2026-11-11.
- Existing repository rollback tag: `codex-restore-20261108-batch65` at
  `b9ce3eed1e9d8f310d6c7fb3e357a9bc0a954eb1`.
- Each follow-up implementation batch must record its commit SHA and immediate
  predecessor so it can be reverted without rewriting branch history.

## First implementation batch

Implemented as Batch 71: a private local proposal/decision ledger references
the existing queue without changing its worker contracts. Research sources
remain caller-supplied and explicitly unverified. The ledger invokes no paid
or external service; accepted proposals create only allowlisted, idempotent
jobs, while rejected/deferred proposals cannot enqueue work. See
[`STUDIO_DIRECTOR.md`](STUDIO_DIRECTOR.md).
