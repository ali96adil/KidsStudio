# M53 — Exact Pi montage lease proof just before Mac FFmpeg

**Scope:** Code on draft PR #28 only. No owner Mac/Pi access, real model,
FFmpeg run on owner media, upload, or change to the default branch.

## Gap after M52

M52 validates frozen Pi scene, recipe and catalogue lineage **when the
worker claims a render job**. The claimed job can become invalid while the
Mac independently validates local files or waits to begin rendering.
A valid claim by itself is not permission to actuate FFmpeg later.

## M53 contract

The authenticated outbound Mac media worker now calls the new narrow
`montage-pre-execution-check` endpoint for every NEW `episode_assemble`
job after it reserves its durable STARTED journal record and immediately
before it invokes the local executor.

The request includes exactly:

- `job_id` (32-character ID)
- `generation` (the current lease generation)
- `payload` (the complete exact Pi-provided render payload, not custom
  paths/commands/models)

The coordinator checks the authorized worker has the episode_assemble
capability, then `StudioQueue.pre_execute_montage` uses one Pi
`BEGIN IMMEDIATE` transaction to check:

- Same current, nonexpired worker+generation+montage lease.
- Exact byte-equivalent parsed request payload, without added fields.
- Studio queue is not paused.
- Current M32/M49/M51/M52 scene/cataloque/recipe provenance, including the
  complete approved scene receipt set, whenever the episode is M32 managed.
- Legacy non-M32 montage jobs retain their existing Pi lease checks and
  Mac M16 original-media preflight.

A mismatch under an otherwise-current lease revokes that lease, marks the
job FAILED with `M53_PRE_EXEC_PROVENANCE_REVOKED`, and records a bounded
`M53_RENDER_PRE_EXEC_REVOKED` audit event. No execution permission is
given. A stale, wrong-worker or expired lease raises an error without
granting a render. Network/clock errors fail closed in the Mac worker.

A successful proof echoes the identical job ID, generation and payload,
with `publication_approved=false` and `render_started=false`. The
Mac validates every response key and value before execution.

If a check fails after the local STARTED reservation, that receipt remains
quarantined and is never automatically retried. Human/owner-authorized
reconciliation is necessary. A previously completed local journal receipt
may be acknowledged without a second render. This stage cannot
guarantee that Pi state stays unchanged *during* an ongoing FFmpeg process;
it prevents stale state at the authorization instant.

## Synthetic regression tests

- Fresh two-scene M32 lease passes the pre-exec gate without rendering.
- Frozen M49 catalogue binding mutates *after lease* and pre-exec fails.
- Pause after lease revokes the job; no FFmpeg executor invocation.
- Wrong worker, wrong generation and changed request payload fail closed.
- Existing legitimate single-clip non-M32 render still completes through
  the new endpoint in a fake-executor integration test.
- M13/M16 synthetic Pi fixtures now return the new exact proof contract.

All tests are software-only with fabricated receipts. A real owner
Mac/Pi link, model suitability, original media bytes, child-safety review,
rights, and final PRIVATE YouTube preview remain separate qualifications.

PR #28 must remain **DRAFT, unmerged**, with no automatic public release.
