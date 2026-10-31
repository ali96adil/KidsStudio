# Kids Studio M68 — Shorts production and Pi handoff

M68 derives 9:16 shorts from approved M67 episode media. Each short has its own
ID, MP4 digest, QA receipt, transfer receipt, M65 render job and inbox entry.
The original episode and shorts must **never share** a render job.

## Execution order

Run commands from the repository root with `python3 -m`. All JSON files
below are examples of filenames, not pre-approved records.

1. `python3 -m kidsstudio.m68_shorts_plan --storyboard examples/m67_colors_red_episode_001.json --output shorts-plan.json`
2. Produce M67 beat art, voice, optional Godot animation, and obtain pinned
   PASS receipts in the M67 asset manifest. The example storyboard alone
   is **DRAFT** and cannot be rendered.
3. Create an existing private output directory under the episode root. Render
   with `python3 -m kidsstudio.m68_portrait_compositor --plan shorts-plan.json --manifest episode-assets.json --root /path/to/episode --output-dir /path/to/episode/shorts`.
   The older `m68_shorts_render` provides a simpler flat-background fallback.
4. For each short run `python3 -m kidsstudio.m68_full_decode --plan shorts-plan.json --short-id SHORT_ID --video /path/to/episode/shorts/SHORT_ID.mp4` and store its JSON output as the decode receipt.
5. Use `m68_short_handoff` to build the immutable digest-pinned inventory.
   Alternatively, `m68_short_qualification` validates all videos in one
   invocation using a JSON mapping from short ID to full MP4 path.
6. Independent content QA must assess educational correctness, language,
   captions, visual clarity, and age suitability. Only a receipt bound to the
   exact MP4 SHA256, source episode and short ID can authorize transfer.
7. Mac: `m68_short_transfer` delegates to M67 SSH/SCP with remote SHA256.
   Existing final files and partial files require reconciliation, not
   blind overwrite. The Pi must have an existing incoming directory.
8. Pi: provision a distinct approved M65 render job and matching M25 plan
   and readiness receipts for **each short**. Run `m68_pi_import_preflight`
   and then `m68_pi_short_import`. Import uses the existing M65 ordinary
   inbox and does not upload to YouTube.
9. Run `m68_release_audit` with the qualification, content-QA and import
   evidence. Its success only means evidence is complete. M65 policy,
   database and one-shot upload journal remain the sole authority for
   **PRIVATE** YouTube upload. The owner reviews the private upload before
   any separate decision to publish.

## Failure and recovery rules

- A failed decode, missing source asset, failed content QA, changed SHA256,
  missing M25 receipt, duplicate short ID or mismatched M65 job blocks progress.
- Do not delete existing Pi staging or re-upload a short to resolve an
  ambiguous network failure. Reconcile the existing M65 upload journal first.
- Never change YouTube visibility to PUBLIC automatically.
- Shorts are optional: if no beat meets educational and duration criteria,
  produce zero shorts rather than fabricating extra material.
- The portrait compositor preserves full source art in a sharp foreground
  panel with a blurred ambient fill. It is **not** object-level 9:16 layout.
  Review text safe areas and character visibility on actual phone screens.
- A successful GitHub test is not a substitute for Mac render, Pi transfer,
  YouTube sandbox/private upload, and owner review.

## Current acceptance boundary

M68 has offline code paths and tests. A production sign-off requires real
Mac FFmpeg/Godot rendering, full decoding, source and output QA, real Pi
transport and M65 inbox acceptance, verified private upload and a restart/
network-interruption test without duplicate uploads.
