# M12 — Pi/Mac to Montage Source Lineage (one-scene pilot)

Development only on draft PR #28. No owner Mac/Pi deployment, no inference, no
model download, no external API, and no private/public YouTube upload.

## Real integration gap

M6 records separate Pi voice and LTX jobs with owner QA; M4 independently
accepts a pinned local MP4. Without a bridge, the montage could use a
different video than the owner-approved LTX result.

The read-only studio-assembly-lineage CLI now requires:

- Approved current script SHA256, both M6 stage owner QA states and exact
  Pi COMPLETED typed job receipts;
- current LTX source_voice SHA equal to the approved voice output;
- the two Mac run directories identified by the Pi job IDs;
- exact actual narration.wav and a2v.mp4 bytes and matching Mac
  stage_receipt.json, including original script SHA, type, job ID, status,
  bytes and artifact SHA256;
- when M10 audio evidence is enabled, the current LTX technical continuity
  report matching both approved WAV and MP4 hashes;
- the montage's EpisodeAssembler recipe pointing at the exact same real
  local LTX MP4, script hash and episode number, with a successful media
  preflight. A separately valid but swapped MP4 is not accepted.

Successful status is SINGLE_SCENE_ASSEMBLY_INPUT_VERIFIED_NOT_RENDERED.
This is no model inference, media rendering, video QA or publishing approval.

## Important implementation limit

M6 currently stores ONE voice + ONE LTX job for each episode. M12 deliberately
allows exactly ONE clip in this bridge. An actual multi-scene educational
episode will require separately approved per-scene job IDs, hashes and
scene-to-assembly lineage. Never claim full multi-scene production success
from this single-scene technical verification.

## Future operator command, after user authorizes device testing

Both Studio Brain SQLite and exact private Mac files must be available in
one authorized environment; M12 does NOT copy any private data between devices.

    studio-assembly-lineage --db /PRIVATE/studio.sqlite \
      --series colors-ar --episode 1 \
      --voice-output-root /PRIVATE/KidsStudio/voice_outputs \
      --ltx-output-root /PRIVATE/KidsStudio/ltx_outputs \
      --assembly-recipe /PRIVATE/KidsStudio/recipes/episode01.json

## Other safeguards completed in M12

- Manual-private-preview readiness now checks staged QA statuses against
  real completed Pi media job receipts, stage types and SHA256 as well as
  source WAV hash, and requires current M10 evidence when that schema exists.
- Mac intake rejects substituted Python binary masquerading as ffmpeg or
  ffprobe; the pinned executables must be distinct, with expected filenames.
  Hash verification is still only a static check, not proof of working FFmpeg.
- Synthetic regression tests cover swapped media, altered Mac receipts,
  rejected duplicate scene counts, current technical audio evidence,
  and forged/incomplete release records.

## Outstanding blockers

Real owner-Mac Chatterbox MLX/LTX 2.3 MLX adapter qualification, scene-level
production, voice B, model and music/voice licensing, final human education
and visual QA, independent verified backup, real episode testing and
owner-approved private preview. PR remains draft and unmerged.
