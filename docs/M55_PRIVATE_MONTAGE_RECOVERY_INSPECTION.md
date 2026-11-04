# M55 — Private quarantined montage inspection, no automatic salvage

## Goal

M54 interrupts local FFmpeg or face-subprocess work when the Mac loses
an authorized Pi montage lease. Partial intermediates and the per-job
`qa_report.json` are deliberately preserved. M55 gives the production
team/agents a **read-only inspection and optional immutable evidence
snapshot**. It is not a resume or rerender mechanism.

## Implementation

`kidsstudio/montage_recovery.py` accepts the **original** Mac
`MediaJournal`, the original 32-hex job ID, the exact original Pi job
payload and the locally pinned media recipe catalogue. It validates:

1. The Mac journal has an unacknowledged `STARTED`
   `episode_assemble` attempt for that job, with matching canonical
   request SHA and recipe ID. `DONE`, absent or different jobs are denied.
2. The M16 pinned Mac recipe/catalogue, original script SHA and scene
   evidence (if multi-scene) are current. It re-runs local-source preflight
   and FFprobe without invoking new models, FFmpeg renders, network
   requests or mutable operations.
3. The per-job run directory and report have no symlink escapes.
   The report must identify the exact run, original recipe SHA,
   source-script SHA, original clip evidence and `publication_approved=false`.
4. Only bounded, recognized output files are SHA-256 hashed and probed:
   `001_normalized.mp4`, similar numbered normalized clips,
   `*_v06.mp4`, `*_v07.mp4` and `episode_qa_master.mp4`.
   Out-of-range, missing, empty, oversized, unprobeable, unexpected or
   symlinked artifacts are clearly noted or fail closed.
5. A normalized file is only a **candidate** if it has 1280×720 video,
   exactly one audio stream and a duration consistent with the original
   pinned clip. A master is only a **candidate** if its duration/shape
   roughly match the expected full episode. Neither proves content,
   fidelity, correct scene ordering, voice identity, lip sync, rights,
   complete M7 decoding, child safety or owner acceptance.

The result always has
`auto_retry_allowed=false`, `auto_reuse_allowed=false`,
`public_release_authorized=false` and
`owner_preview_approved=false`. M55 never updates the Pi queue, the
Mac journal, the original media, the partial render directory or any
approval record. The CLI uses a read-only SQLite journal locator and
will never initialize an absent journal.

### Optional immutable evidence freeze

Using `--freeze-evidence` explicitly writes a single immutable JSON
envelope into `<private output root>/_recovery_evidence/<job-id>.json`,
containing the inspection and a canonical SHA-256 of its report.
It uses exclusive create and fsync; a second attempt cannot overwrite
the original snapshot. The stored record is **not authorization** to
reuse or publish.

### Offline usage — only after device qualification

```sh
python -m kidsstudio.montage_recovery \
  --recipes /PRIVATE/recipes.json \
  --journal /PRIVATE/media_receipts.sqlite \
  --job-id ORIGINAL_32_HEX_JOB_ID \
  --payload-json /PRIVATE/original_pi_render_payload.json
```

The `--payload-json` file contains the exact original JSON payload
(`recipe_id`, `script_sha256` and optional `catalogue_sha256`).
For a deliberate evidence archive, add `--freeze-evidence`.
Replace placeholders with original owner-controlled private paths.
Do **not** run this against a live or unknown job: it is intended
exclusively for already-quarantined attempts.

## Regression checks

- An aborted synthetic job yields a normalized *candidate*, never a
  ready-for-reuse or publishing decision.
- The original Mac STARTED receipt matches an exact request SHA.
  A wrong payload, other job or DONE record fails closed.
- Changes to script or recipe SHA reject the inspection.
- Symlinked/unknown content cannot be silently promoted.
- Corrupt/unprobeable MP4 is explicitly non-reusable.
- Evidence can be frozen once without modifying the journal, original
  script or clip; no replacement is permitted.
- Missing journal path never creates a new journal during inspection.

### Important fixed bug

M55 corrects the initial `qa_report.json` status for an active
`EpisodeAssembler` run. It was unintentionally overwritten by the
read-only preflight status. Active run manifests now correctly start
as `STARTED`; pre-M55 interruptions with the older status are
still recognized as quarantined.

## Not yet implemented

**No automatic resume, clip import, partial promotion, queue retry or
snapshot-based trust elevation.** A future M56 may create a new
owner/AI-reviewed plan with fresh job ID, bounded stage-specific salvage
and complete final M7/rights/child-safety checks. M55's report cannot
replace Pi-side M49–M54 scene and lease checks.

This is source-level and synthetic qualification only: no real
Mac/Pi device access, real original media, live GPU AI, TLS link
or YouTube publishing. Keep PR #28 **DRAFT and unmerged**.
