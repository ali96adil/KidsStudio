# M60 — Fresh recovery job ID reservation; NO claimable job yet

**State:** Experimental development branch, PR #28 (DRAFT, unmerged).
No actual Mac/Pi qualification, no run against owner's sources, no
YouTube authorization/upload, no inference or FFmpeg output.

## Why M60 reserves rather than immediately enqueues

Existing M52, M53 and M54 protect ordinary `episode_assemble`
jobs using M32/M49/M51 frozen catalogue and a specific linked episode
`render_job_id`. A recovered media recipe has **different** selected
scene SHA-256 values and intentionally uses **schema version 2**.
If we pushed it into the existing queue as an ordinary montage, it would
either be rejected by M52, or require relaxing those safeguards.

M60 does **not** relax M52–M54 or let an unknown worker claim the
new job. Instead it atomically reserves a different 32-hex future job ID
under a dedicated Pi table. That identity is **not a queue job**, has no
lease, and is not yet executable. The next milestone must add a distinct
worker capability, strict recovery claim/heartbeat and a special media
assembler which can skip normalization for already-normalized media.

## Pi: M60 reservation with CURRENT lineage checks

`kidsstudio/recovery_execution_admission.py`:

1. `initialize` adds `studio_recovery_reservations` to the existing
   Studio Brain database without overwriting an earlier record.
2. `reserve` requires the exact copied private M56 proposal, the
   private M59 **non-executable schema-2** staged recipe, and the M59
   schema-2 manifest, each with an exact SHA-256 of its copied file
   contents. All current source selections, source SHAs, scene order,
   face-cleanup policies, negative auto-execute and publication flags
   are checked.
3. Under a single `BEGIN IMMEDIATE` transaction, the original
   **FAILED/CANCELLED** Pi render, its **BLOCKED** episode, active
   series, exact original M32 plan, M49 catalogue/scene set, M51
   render contract and independent voice/LTX/audio QA receipts are
   checked AGAIN through the M57 verifier.
4. The M57 intent, M58 media binding and M59 staged-recipe binding must
   all match the exact source SHA, manifest SHA, scene lineage and
   proposal ID. Missing or replayed data is rejected.
5. One fresh UUID is reserved, distinct from the failed job.
   It is written **only** to `studio_recovery_reservations` in state
   `M60_RECOVERY_JOB_RESERVED_NOT_DISPATCHABLE`.
   It is **never inserted into `jobs`**, so an ordinary worker cannot
   claim it. The audit event references the original failed job.
6. The reply contains `job_inserted_in_queue=false`,
   `worker_claimable=false`, `auto_execute_allowed=false`,
   `public_release_authorized=false`.
   The Pi does NOT claim independent verification of actual Mac
   recovered video bytes.

The system admission test is NOT an extra manual per-scene review.
Existing AI/script/media QA receipts are checked as technical
requirements; the owner still reviews the final PRIVATE video before
any proposed publication decision.

## Mac: fresh read-only source gate

`kidsstudio/recovery_local_gate.py` recomputes the complete M59
recipe using the original Mac STARTED journal, unchanged approved
script and LTX clips, and fresh M7 full-decode of every reused
normalized scene. It compares the **exact bytes** of the previously
frozen schema-2 M59 recipe and canonical manifest against the current
recomputation, with no command execution and no write. A changed
source, recipe, manifest, old job, or occupied output run ID blocks
the gate.

The Mac returns `M60_MAC_STAGED_MEDIA_RECHECKED_NOT_EXECUTED`;
a successful result is NOT a Pi lease.

## Synthetic regression coverage

- Pi reservation once with a new unique ID, **zero** new queue jobs.
- Duplicate/replayed reservation is rejected.
- Incorrect source SHA, changed recipe/manifest, positive auto-execute
  flag, revoked scene QA or old job state are rejected.
- Mac rechecks the fully frozen staged recipe and refuses byte
  modifications while keeping the journal and sources unchanged.
- Existing schema-1 `EpisodeAssembler` continues rejecting the
  schema-2 staged recipe, which is not added to MediaRecipes.

## Reference-only commands — do not run on owner devices yet

```sh
python -m kidsstudio.recovery_execution_admission \
  --db /PRIVATE/pi/studio.sqlite --initialize

python -m kidsstudio.recovery_execution_admission \
  --db /PRIVATE/pi/studio.sqlite \
  --proposal /PRIVATE/pi/copied_m56.json \
  --proposal-sha256 EXACT_M56_FILE_SHA256 \
  --recipe /PRIVATE/pi/copied_m59_recipe.json \
  --recipe-sha256 EXACT_M59_RECIPE_FILE_SHA256 \
  --manifest /PRIVATE/pi/copied_m59_manifest.json \
  --manifest-sha256 EXACT_M59_MANIFEST_FILE_SHA256

python -m kidsstudio.recovery_local_gate \
  --recipes /PRIVATE/mac/owner_catalogue.json \
  --journal /PRIVATE/mac/media_journal.sqlite \
  --original-job-id FAILED_32_HEX_JOB_ID \
  --original-payload /PRIVATE/mac/original_job_payload.json \
  --proposal-id NEW_32_HEX_PROPOSAL_ID
```

## M61 implementation needed for a real recovery render

Add `recovery_assemble` to a dedicated, strictly allowlisted media
worker capability **only with** a new atomic claim guard and
pre-execution/heartbeat revalidation, explicit owner/system authorization,
Mac recipe revalidation and a specialized FFmpeg assembly path.
Insert a real queue job for the RESERVED identity only after all
guards exist. A recovered normalized clip must not be unnecessarily
re-encoded; the new master and its scene ordering/audio still require
complete M7 quality, educational safety, licensing and final PRIVATE
owner preview. No public visibility is granted.

Keep PR #28 DRAFT and unmerged until full CI and owner device
qualification.
