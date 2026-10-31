# M68 Shorts — release gate (2026-10-31)

## Implemented
- Derived-short plan, vertical rendering, media decode/hash checks.
- Separate Shorts registry, six-axis review receipts, Pi staging checks.
- Shared M26 daily quota reservations and one-shot attempt journal.
- PRIVATE-only YouTube transport, upload-response ID pinning and authenticated privacy verification.
- Atomic review/policy revalidation when recording upload attempt.

## Production blockers
1. Source provenance: source_episode_id is not yet securely bound to an approved studio_episodes row and approved master render receipt. A string ID is not proof.
2. Pi deployment: OAuth storage/refresh, transfer permissions, service launch and dashboard controls need end-to-end validation.
3. Quota lifecycle: unknown upload outcomes require operator reconciliation; do not expire attempted reservations automatically.
4. Review execution: six-axis results are persisted, but autonomous AI reviewer execution is not yet integrated.
5. Real upload: CI and Godot smoke do not verify an actual YouTube upload from Pi.

## Acceptance before unattended operation
- Provenance pinned to approved episode, source master SHA and series.
- Pi staging and local SHA verified from a trusted catalogue.
- Concurrent quota tests and crash/timeout reconciliation without duplicate uploads.
- One controlled real PRIVATE Pi upload verifies video ID, channel, privacy and processing.
- Owner can accept/reject/comment on private draft; PUBLIC always requires separate explicit approval.
- CI green on the final commit.

**Release decision: BLOCKED. Do not enable unattended Pi uploads or automatic public publication.**

## Operator preflight (read-only)

Before any one-shot upload, call `kidsstudio.m68_pi_preflight.assess(queue, short_id=..., series_id=..., media_path=Path(...))` on the Pi. A result of `READY_FOR_EXPLICIT_PRIVATE_UPLOAD` is only a diagnostic, **not permission to publish or to skip the owner policy**. Every blocking reason must be resolved before explicit invocation. The uploader rechecks the critical policy and QA in its own transaction.

Never place OAuth tokens in Git, episode metadata, upload receipts or UI logs. Provide a fresh token at invocation and do not log it. Do not schedule retries for `STARTED_UNCERTAIN` or `MANUAL_RECONCILIATION`. Reconcile unknown uploads in YouTube Studio before any new upload.

## Recent engineering updates

- M26 `_approved` source render receipt and 11-axis quality gate are checked when binding and before attempting a Short upload.
- A new read-only Pi preflight reports actionable blockers without Google network calls.
- A unique partial index prevents the same YouTube video ID being recorded for two Shorts.
- Test coverage includes forged source receipt, changed media, revoked source and duplicate attempts.

This is a **code-complete candidate for local integration testing only**, not a certified unattended production pipeline. The actual Pi environment, credentials, agent review implementation and one controlled real PRIVATE upload remain outstanding.
