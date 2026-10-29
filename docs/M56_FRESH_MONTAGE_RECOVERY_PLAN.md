# M56 — Fresh private montage attempt proposal, no hidden replay

**Scope:** Draft PR #28, synthetic tests and local-only code. No Mac/Pi
owner hardware, no actual AI model inference, no YouTube upload, and no
modification of the production main branch.

## Purpose

M55's frozen inspection of an aborted `episode_assemble` identifies
potentially usable normalized scene MP4s, but *only as candidates*.
M56 proposes how a **different future attempt** might reuse original
content safely and avoid redoing expensive Chatterbox/LTX generation.
M56 does not authorize an existing job, bypass scene approvals, or rerun
any work automatically.

## Plan builder

`kidsstudio.montage_recovery_plan` reads the original Mac STARTED
journal, the exact original Pi job payload and the **immutable M55
`_recovery_evidence/<old-job-id>.json` snapshot**. It re-runs the
M55 inspection and requires an exact canonical match with that snapshot,
rejecting changed source bytes, changed report hashes, altered files,
injected extra artifacts or stale media receipts.

A distinct 32-hex `proposal_id` is mandatory; it is **not a Pi job
ID**. The planner must not overwrite an existing proposal or render
directory.

For every source scene in original order:

- If M55 found a normalized 1280×720 candidate, M56 checks its exact
  SHA again and runs the M7 technical media gate, including **real
  FFprobe and complete FFmpeg decode** with the original expected SHA.
- It only selects a recovered candidate when every M7 check succeeds,
  technical status is `TECH_PASS_OWNER_REVIEW_PENDING`, and
  `rights_verified`, `subjective_checks_performed` and
  `publishing_approved` remain false. Technical pass means media
  plausibility, NOT permission to use or publish.
- Missing, corrupt, unprobeable, too-short or otherwise failed
  candidates fall back to the existing original *hash-pinned* LTX
  scene MP4. This avoids rerunning LTX/voice generation; the future
  montage still needs a new FFmpeg pass.
- Any suspicious unexpected artifact or changed original source causes
  the whole proposal to fail closed.

The result lists a separate candidate path + SHA for every ordered
scene, original source and face cleanup metadata, counts of normalized
candidates/fallbacks, original M55 snapshot fingerprint and exact
original script/catalogue provenance.

It **never** emits an executable M14 recipe, patches an original M14
scene seal, modifies an immutable M49 binding, queues a task, assigns
a worker lease, runs FFmpeg, alters a Pi/SQLite job, accepts owner
preview or uploads video.

### One-time proposal freeze

`freeze_private_montage_recovery` exclusively creates a single private
JSON envelope under
`<private output root>/_recovery_proposals/<proposal-id>.json`.
The envelope contains the proposal and its canonical SHA-256. No
overwrite, queueing or execution occurs. Source files and journal
remain untouched.

### Offline CLI (after the owner authorizes device tests)

```sh
python -m kidsstudio.montage_recovery_plan \
    --recipes /PRIVATE/frozen_catalogue.json \
    --journal /PRIVATE/media_receipts.sqlite \
    --original-job-id ORIGINAL_32_HEX_JOB_ID \
    --original-payload-json /PRIVATE/original_payload.json \
    --proposal-id NEW_32_HEX_PROPOSAL_ID \
    --freeze
```

`--freeze` is optional; without it the tool only prints an inspection
and never creates any file. The private paths shown are placeholders;
the command is not yet an instruction to run on the real Mac.

## Guardrails still required before a new queued attempt

1. A fresh Pi-authorized job/lease identity (different from the old job);
   the proposal ID is **not** that identity.
2. A new M14/M49-compatible scene lineage contract, or an explicitly
   reviewed extension that supports transformed normalized artifacts
   while preserving the original approved WAV/LTX scene provenance.
   Existing M51 immutable recipes and M49 bindings cannot be quietly
   substituted or overwritten.
3. Re-check current source/scene approvals and M52–M54 lease
   validity. All inputs and outputs must stay in private storage.
4. Full M7 technical and AI quality/rights checks on the NEW
   **assembled master**, plus the existing PRIVATE-only owner preview.
5. No automatic public visibility or implied publisher authorization.

Until these gates are integrated, M56's output is a **proposal only**,
not a render-ready job.

## Tests

Nine synthetic regressions cover exact candidate selection, approved
source fallback, refusal after failed full-decode claim, one-time
non-overwritable proposal snapshot, stale/tampered M55 evidence, wrong
old journal state, unexpected output files, and false publishing flags.
These tests use an isolated two-scene synthetic fixture with a fake
M7 checker to assert the planner's selection policy; the real default
uses full FFmpeg decode. M13/M14 seal checks have independent repository
regressions. These are not equivalent to an end-to-end real Mac/Pi
qualification.

Leave PR #28 DRAFT and unmerged.
