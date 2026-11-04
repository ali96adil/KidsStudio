# M50 — Atomic final-montage dispatch under immutable coordinator fences

**Status:** Code + synthetic regression tests on draft PR #28 only. No owner
Mac/Pi installation, real model inference, OAuth, upload, merge or publication.

## Gap after M49

M49 checks the actual owner-transferred frozen Mac M14 JSON catalogue and
matching scene evidence before recording a one-time Pi binding. However,
M32's `status` / `tick` checked the binding and scene plan on a read
connection, then invoked `SeriesManager.queue_render` in a later,
independent SQLite write transaction. Even if the earlier snapshot was
green, a source of truth could change between these steps. A newly queued
job might then refer to a stale scene-plan hash or binding.

## M50 dispatch fence

For renders originating from the M32 StudioOrchestrator, the exact pinned
M32 plan SHA is passed to `SeriesManager.queue_render`. For deferred
`AFTER_SCENE_QA` plans, a required binding flag is passed too.

Before writing the job, while holding the **same SQLite write transaction**
as the queue insertion, `queue_render` now rechecks:

- Queue remains unpaused and script remains approved (existing requirements).
- Series is ACTIVE and its original approved script SHA matches the
  `studio_orchestrator_plans` row.
- Current registered scene-plan SHA exactly matches the immutable M32 pin.
- Every scene still has valid owner QA, exact voice/LTX receipts and audio
  compatibility evidence (existing multi-scene validation).
- For deferred montage, `studio_orchestrator_assembly_bindings` still
  has the exact M32 plan SHA, the catalogue SHA selected by the tick, and
  the SHA of the **current complete approved scene receipt set**.

Any mismatch raises `SeriesError` and rolls back the transaction. No
render job or episode state transition occurs. Existing owner-authorized
non-orchestrator queue calls retain their earlier safety gates and API.

## Regression coverage

Synthetic two-scene M32 tests inject two changes **after** `tick` has
observed a green plan and **before** `queue_render` is entered:

1. The recorded scene-plan SHA changes.
2. The one-time bound catalogue SHA changes.

Both must reject the render and leave zero queued jobs and the episode
in SCRIPT_APPROVED state. Existing tests also cover a valid deferred
two-scene render and the older pre-pinned catalogue route.

## Limits and next real-world gate

SQLite transaction isolation protects the Pi-local source-of-truth
and queue operation. It does **not** cryptographically attest a remote
Mac, independently confirm production model accuracy or license status,
or prevent external files from changing. The Mac M16 worker must still
read its ORIGINAL private catalogue and verify original media hashes
before FFmpeg. An actual two-device owner-authorized trial, independent
content review and a PRIVATE YouTube owner-preview remain unqualified.

Keep PR #28 in DRAFT and do not deploy or publish automatically.
