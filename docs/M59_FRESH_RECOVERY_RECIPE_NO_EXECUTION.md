# M59 — Fresh staged recovery montage recipe; non-executable by design

**Status:** Development-only, PR #28 (DRAFT, unmerged). No original
Mac/Pi hardware, no actual media, model or cloud call, and no YouTube
upload/public exposure.

## Result

M55 stored an immutable forensic inventory of interrupted private clips.
M56 proposed a *different* recovery attempt with each scene in the
original approved order. M57 pinned its intent on Pi; M58 revalidated
the media bytes on Mac and bound an independent media-hash contract on
Pi. M59 now prepares a **new versioned staged recipe**, but refuses to
run it until a later explicit authorization path is implemented.

### Mac — independent staged recovery recipe

New `kidsstudio/recovery_execution_recipe.py`:

- Requires the exact original unacknowledged Mac journal STARTED record,
  current SHA-pinned original M4 recipe, frozen M55/M56 evidence and
  frozen M58 media contract; freshly hashes all input bytes and runs M7
  complete FFmpeg decode for every candidate proposed for reuse.
- Reconciles the current M58 contract byte-for-byte against its frozen
  snapshot. A changed file, mismatched script SHA, old job ID or
  altered scene order fails closed.
- Assembles a new scene recipe *without changing old media files*.
  Recovered normalized clips use their unchanged 1280×720 output
  and `face_cleanup=none` (already face-processed); other scenes use
  their exact original approved LTX source and original face option.
  This **avoids regenerating Chatterbox voice and LTX animation**.
- Writes a unique recipe at
  `_recovery_recipes/<proposal-id>.json` and distinct approval
  metadata at
  `_recovery_execution_manifests/<proposal-id>.json` in the existing
  private output root. Both use `O_EXCL` (no overwrite) and fsync.
- The staged recipe intentionally uses `schema_version=2` and
  `recovery_stage=M59_STAGED_ONLY_NO_EXECUTION`.
  **EpisodeAssembler currently accepts only schema 1**, so even
  direct calls to the old assembler cannot execute this new recipe.
  The separate metadata envelope is also schema 2, containing selected
  scene SHA-256 and original LTX SHA, original plan/catalogue
  fingerprints, counts and `auto_execute_allowed=false`.
- Does not create or register an executable `MediaRecipes` catalogue,
  enqueue a job, run FFmpeg rendering, rewrite Pi M49 binding or mark
  media publication-ready.

The staged recipe is a *source recipe blueprint*, **not** a runnable
M4 recipe. Recovered normalized clips will require a special,
Pi-authorized M60 compile/execute path so that future assembly can
skip unnecessary re-normalization instead of doing an extra FFmpeg pass.

### Pi — SHA-pinned non-executable staging contract

`RecoveryIntake.initialize()` adds
`studio_recovery_execution_recipes` to the existing operational DB.
`RecoveryIntake.bind_execution_recipe` accepts the copied M56
proposal, M59 staged recipe and M59 manifest, each with the SHA-256 of
its exact transferred bytes. Within one SQLite `BEGIN IMMEDIATE`
transaction it:

- Rechecks the original FAILED/CANCELLED montage and BLOCKED episode,
  original M32/M49/M51 plan, scene-set SHA, current independent
  voice/LTX/audio QA receipts and exact old queue payload;
- Requires an existing immutable M57 proposal and current M58
  media-selection contract for the same proposal ID;
- Compares every scene in the schema-2 recipe/manifest against M56
  source path, LTX SHA, selected source SHA, recovery strategy and
  already-applied face cleanup. Recovered segments must declare a
  completed *technical* M7 check; original fallbacks retain original
  face cleanup;
- Rejects unknown/missing fields, wrong SHA, changing M58 contract,
  conflicting job identities, retry/publication flags, replay and
  substitutions;
- Pins the distinct `recovery_<32-hex-id>` recipe identifier and
  hashes, in state `M59_NONEXECUTABLE_RECIPE_BOUND`, with **zero**
  new jobs queued.

Pi cannot independently verify original Mac bytes from a transferred
SHA manifest; `mac_bytes_verified_by_pi=false`. Nor is a copied SHA a
cryptographic signer attestation.

### Synthetic test coverage

- Mac: one recovered clip and one original fallback become a fixed
  ordered recipe; script and scene/source hashes stay pinned.
- Mac: no write during dry-run, immutable one-time private freeze and
  rejection of mutated recovered bytes.
- Mac: the original schema-1 `EpisodeAssembler` refuses even the
  frozen schema-2 recovery recipe (no standalone bypass).
- Pi: staged recipe+manifest bind without job creation, deterministic
  recipe identity, one-time-only import, wrong source SHA, failed
  M7 claims, invalid face stage, forged new job/public flag, changed
  original job and mismatched transferred-file bytes all fail closed.

### Offline reference (not for owner devices yet)

On Mac:
```sh
python -m kidsstudio.recovery_execution_recipe \
  --recipes /PRIVATE/owner_catalogue.json \
  --journal /PRIVATE/owner_media_journal.sqlite \
  --original-job-id ORIGINAL_32_HEX_JOB_ID \
  --original-payload-json /PRIVATE/original_payload.json \
  --proposal-id NEW_32_HEX_PROPOSAL_ID --freeze
```

On Pi, after M57 and M58 have been bound:
```sh
python -m kidsstudio.recovery_intake --db /PRIVATE/pi/studio.sqlite \
  --bind-recipe \
  --proposal /PRIVATE/copied_m56_proposal.json \
  --sha256 EXACT_COPIED_M56_SHA256 \
  --recipe-file /PRIVATE/copied_m59_staged_recipe.json \
  --recipe-sha256 EXACT_COPIED_M59_RECIPE_SHA256 \
  --execution-manifest /PRIVATE/copied_m59_manifest.json \
  --execution-manifest-sha256 EXACT_COPIED_M59_MANIFEST_SHA256
```

Commands above are reference material only; no real device qualification
is claimed.

## M60 required before any execution

M60 must add an explicit owner-authorized Pi queue transition for this
specific M59 recipe plus a fresh unique job ID, new M14-like scene
lineage, pre-execution/heartbeat guards adapted from M52–M54, and
live Mac SHA rechecks. It should skip re-encoding already-normalized
segments while still assembling a **new** master and running full
M7/AI/rights/educational quality review, followed by the owner's
PRIVATE preview and approval.

Do not merge PR #28, run M59 recipes with old CLI, or promote media to
PUBLIC. Stage M59 is intentionally NOT an executable release.
