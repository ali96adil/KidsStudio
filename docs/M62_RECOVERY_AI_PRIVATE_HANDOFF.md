# M62 — Recovered-master QA and PRIVATE-only upload handoff

**Status:** Draft PR #28, not merged. This is a metadata/QA bridge,
not an authenticated YouTube uploader. Nothing in M62 contacts Google,
changes visibility, or assumes that a video was uploaded. Owner Mac/Pi
hardware has not been exercised for this release.

## Problem

M61 produces an entirely new private recovery master under a
`recovery_assemble` identity that is deliberately *not* registered as
the legacy `episode_assemble` job. M7/M27/M26 and the existing
PrivatePreviewReview module explicitly check the old, completed Pi job
and episode state. Changing the old job's ID or setting the BLOCKED
original episode to EPISODE_APPROVED would create an unsafe shortcut.
M62 therefore keeps **separate immutable recovery QA receipts**.

## M62 Pi ledger

`kidsstudio/recovery_final_qa.py` initializes:
- `studio_recovery_final_qa`: one exact recovery proposal ID/job ID,
  M61 final master SHA, approved original script SHA, M7 technical
  report SHA, optional independent AI evidence/rights SHA references,
  two distinct provider identities, and a fail-closed status.
- `studio_recovery_private_handoffs`: one SHA-bound owner-policy
  PRIVATE handoff for a particular channel/audience/synthetic-media
  disclosure and owner policy revision. This is **not** a YouTube job.

Each mutation takes a Pi SQLite `BEGIN IMMEDIATE` write transaction
and revalidates current M61 completed lease and original M57–M60
lineage, original FAILED/CANCELLED render, BLOCKED episode, original
M32/M49/M51 plan and voice/LTX/audio QA receipts. A stale scene, source
script, reservation or final master blocks registration.

### 1. Fresh full M7 master verification

The Mac uses the existing independent `episode_quality.inspect_video`
and `save_report` to run FFprobe, SHA256, H264, AAC, exact
1280x720 24 FPS, 48kHz audio and complete video/audio FFmpeg decode.
The M62 CLI defaults to dry-run. Only `prepare-technical --execute`
creates a new *exclusive private* report. It never uploads.

The report is transferred to Pi as metadata; Pi checks the complete
M7 gate, checks its master SHA against the exact M61 completion
receipt, and records its own report file SHA. A Pi report SHA **does
not mean the Pi directly inspected Mac media bytes**. No subjective
child-safety/rights/educational approval is inferred from FFmpeg.

### 2. Two independent AI reviews and asset-rights evidence

The `register-ai` operation reuses the M27 final QA format:
`pedagogy_language` and `visual_child_safety` must be assessed by
two different providers, and each role must supply written evidence
for its five criteria. The inputs include exact hash references to
a complete transcript, sampled video frames, decoded audio analysis
and a *separate* rights/provenance catalogue covering all assets and
commercial YouTube Kids scope.

Every criterion must be PASS for the state
`M62_AI_INTERNAL_READY_PRIVATE_ONLY_NOT_UPLOADED`.
Any NEEDS_FIX/UNSURE decision stores a durable
`M62_AI_INTERNAL_CHANGES_REQUIRED` outcome and a series triage note;
it **cannot** be treated as approval. The modules validate
consistent evidence and independence declarations; they cannot prove
that an AI actually watched each frame, that the judgments are
correct, or that a copyright claim is legally settled. These
limitations remain visible in the result.

No per-scene owner review is inserted in the automated QA pipeline.
The owner makes the final video decision after a verified PRIVATE
YouTube preview, with comments and revision suggestions.

### 3. Owner-scoped private handoff only

`stage-private` requires internal AI state READY and the existing
M26 standing owner policy to be **ENABLED**, for the exact approved
YouTube channel, children audience classification, and synthetic
media declaration. It pins the current policy revision and the exact
M61 master/AI review SHA under
`M62_PRIVATE_UPLOAD_HANDOFF_STAGED_NOT_QUEUED`.

The original M26 uploader *cannot* accept M61 recovery identities;
its M26 readiness guard still requires an ordinary
EPISODE_APPROVED original render. M62 does **not**:
- rewrite the original job, replace its render receipt or change
  the BLOCKED episode state;
- create an ordinary YouTube upload job or M25 upload journal;
- call YouTube, OAuth, or HTTP;
- claim a PRIVATE video exists;
- authorize any PUBLIC visibility, schedule, or publication;
- bypass the owner's post-PRIVATE comments/approve/notes/revise
  workflow.

M63 must implement an **explicit recovery-only M26-equivalent private
uploader/verification bridge** with independent lease/policy revision
rechecks, exact Mac media bytes and M7/AI source SHA, idempotent
YouTube upload, and M24 owner feedback storage. M63 must not relax
existing M26 gates for ordinary videos.

## Offline commands (reference; do not run on owner devices yet)

On Mac, after completed M61 montage:
```sh
python -m kidsstudio.recovery_quality_cli prepare-technical \
  --video /PRIVATE/mac/renders/RECOVERY_JOB/episode_qa_master.mp4 \
  --sha256 EXACT_M61_MASTER_SHA256 \
  --report /PRIVATE/mac/m62_technical.json --execute
```

On Pi, after copying JSON evidence privately:
```sh
python -m kidsstudio.recovery_quality_cli initialize \
  --db /PRIVATE/pi/studio.sqlite

python -m kidsstudio.recovery_quality_cli register-technical \
  --db /PRIVATE/pi/studio.sqlite \
  --proposal-id M56_32_HEX_ID --report /PRIVATE/pi/m62_technical.json

python -m kidsstudio.recovery_quality_cli register-ai \
  --db /PRIVATE/pi/studio.sqlite \
  --proposal-id M56_32_HEX_ID \
  --bundle /PRIVATE/pi/m62_agents.json \
  --observed /PRIVATE/pi/m62_observation.json \
  --rights /PRIVATE/pi/m62_rights.json

python -m kidsstudio.recovery_quality_cli stage-private \
  --db /PRIVATE/pi/studio.sqlite \
  --proposal-id M56_32_HEX_ID \
  --channel-id OWNER_APPROVED_CHANNEL_ID \
  --made-for-kids yes --synthetic-media yes
```

**No command above uploads or changes the YouTube visibility.**
The ordinary upload system remains unchanged. M62 data is exposed on
the owner overview dashboard with explicit *not uploaded* statuses
and no local source paths.

## Tests

Synthetic two-scene M32/M49/M51/M57–M61 fixtures verify:
- exact M61 completed recover job/master and full M7 report SHA;
- duplicate or forged technical evidence is blocked;
- two different educational/visual provider identities and ten
  documented criteria plus separate documented asset rights;
- unsure child-safety decision cannot stage a handoff;
- source scene QA revocation blocks AI review;
- standing owner private channel policy is required and cannot be
  bypassed; duplicate handoff fails;
- zero new queue jobs, zero network/OAuth, unchanged original
  blocked episode, and private dashboard states;
- CLI dry-run does not call FFmpeg.

Synthetic fixtures are *control-flow* verification, not evidence of
correct AI judgments or legal rights. Maintain PR #28 as DRAFT until
real Mac/Pi and YouTube PRIVATE-only qualification.
