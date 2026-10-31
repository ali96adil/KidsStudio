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
