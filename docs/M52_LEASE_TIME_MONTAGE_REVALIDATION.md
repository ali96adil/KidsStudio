# M52 — Verify final montage again at Mac-worker lease time

**Status:** Development-only draft PR #28. No owner devices, real generative
models, credentials, remote workers, publishing, or main-branch changes.

## Why a second validation?

M49 checks the transferred frozen M14 catalogue and scene evidence before
binding. M50 checks the exact current binding and scene plan atomically when
enqueuing a montage. M51 denies manual/CLI bypass for M32-pinned episodes.
There is still time between render enqueue and a Mac worker's later claim.
A deferred job can become stale after enqueue due to a changed scene receipt,
series state, render contract, or frozen catalogue binding.

## M52 implementation

`kidsstudio.render_claim_gate.m32_montage_claim_blocker` performs a **read-only
validation inside the same Pi SQLite BEGIN IMMEDIATE transaction as
`StudioQueue.claim`**. For a queued `episode_assemble` linked to an M32
episode it rechecks:

- Active series and RENDER_QUEUED episode with matching render_job_id,
  original approved parent script hash, render attempt and idempotency key.
- Canonical typed payload: exactly the pinned recipe ID, episode script SHA
  and a 64-character exact catalogue SHA.
- M51 immutable M32 render contract and parent scene-plan SHA.
- Full, contiguous original scene identity fingerprint.
- Every current approved scene's voice and LTX job completion, voice-to-LTX
  link and required technical-audio evidence through `assert_scenes_ready`.
- For AFTER_SCENE_QA, the original M49 binding's plan, frozen catalogue,
  evidence SHA and the current complete scene-set hash.
- For pre-pinned legacy M32 plans, the exact immutable catalogue SHA.

When M32 has active pinned plans, even a raw `episode_assemble` queue job
**not linked to an episode render_job_id** cannot bypass the M32 lease gate.
Older, not-M32-managed workflows remain compatible with existing gates.

On any mismatch the queue marks that job FAILED with
`M52_CLAIM_PROVENANCE_REVOKED` and an audit event identifying the bounded
reason. It does not grant a lease, run FFmpeg/models, retry, or publish.
A later explicit owner reconciliation of the episode is required.
The Pi coordinator's authenticated `claim` endpoint already calls this
`StudioQueue.claim` method, so it inherits the gate without allowing
a new arbitrary remote operation.

## Synthetic regression tests

- An unchanged deferred two-scene render gets exactly one Mac-worker lease.
- The bound catalogue SHA changes after enqueue: lease is revoked.
- The second scene's approved LTX artifact SHA changes: lease is revoked.
- The pinned montage recipe ID changes: lease is revoked.
- A raw unlinked montage queue insertion cannot evade an existing M32 plan.

## Trust boundary

This is Pi-local transaction-time provenance validation, not a cryptographic
attestation that the remote Mac contains the claimed media bytes. M16 still
verifies the ORIGINAL local Mac media/catalogue and all relevant SHA pins
before FFmpeg. A job may also change after leasing; the next hardening
phase can add a just-before-execution reauthorization. Neither synthetic
tests nor this gate qualify actual model accuracy, source licensing, child
safety or a YouTube publication. Owner review and PRIVATE-only policies
remain in force.

Keep PR #28 **draft and unmerged** until the owner-authorized full test.
