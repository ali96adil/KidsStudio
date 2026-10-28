# M13 — Ordered, independently approved scenes for real episodes

**Code-only in GitHub draft PR #28; no owner Mac/Pi deployment.**
No real Chatterbox/LTX model was run, no media generated on user devices,
no outside API calls and no YouTube upload.

## What was missing

M6 originally had ONE voice and ONE LTX job per EPISODE. That is enough for
a technical one-clip pilot but not for a meaningful multi-scene educational
episode. M13 adds an additive Studio Brain schema with separate scene
scripts, jobs, QA and audio-continuity evidence. Existing single-scene
records are not silently migrated.

## Owner-approved scene plan

A separate private JSON file with:
- schema_version=1
- series_id and episode_number
- episode_script_sha256 matching current owner-approved full script
- 2–40 ordered scenes numbered 1..N
- each scene has an exact scene-script SHA256 plus objective (5–220 chars).

Scene script and character assets stay PRIVATE on the Mac. The Pi stores
scene number, objective and hash only, not script text or model weights.
Registering a plan is explicit and immutable per episode; a revised plan
requires a deliberate new episode revision/migration, not silent overwrite.

## Independent per-scene state machine

Each scene voice and LTX job is a typed, bounded Studio Queue media job using
the existing Pi coordinator and Mac Media Worker security model.
- voice_synthesize is queued using a scene-specific approved script SHA.
- A2V for that scene cannot queue until that scene's WAV was completed and
  owner QA-approved.
- LTX payload pins the EXACT approved scene WAV SHA.
- A2V waits for owner-recorded technical audio continuity evidence matching
  the exact WAV and resulting MP4.
- Owner THEN visually reviews the scene and approves its actual A2V SHA.
- Failure is BLOCKED. No blind automated retries; this initial schema has
  no automatic retry/replacement path.
- The full parent episode cannot queue final assembly while ANY scene is
  missing either approved stage, matching Pi receipt or audio evidence.

The strict acceptance read checks exact media SHA and completed typed Pi
queue result for each scene, scene-script lineage, audio evidence and
contiguous scene numbering. All scene records must be consistent.

## From scenes to actual M4 assembly inputs

The read-only studio-scene-assembly preflight reads the canonical Pi SQLite
and local Mac stage folders and validates each actual WAV/A2V file against
the owner-approved scene job, SHA and Mac stage_receipt.json. It validates a
private template that names the current approved full script, output root,
the M4 face scripts, FFmpeg and FFprobe, and a face_cleanup_by_scene list.

Preflight does not create any file. With an explicit --write-recipe PATH,
it creates ONE NEW immutable private JSON recipe in the normal M4
EpisodeAssembler schema, with clips in the exact 1..N order. It never
overwrites existing recipes or renders the video itself.

The M4 assembler will still use its own preflight, face-geometry checks,
normalization, FFmpeg and video QA. A generated recipe is NOT an owner
approval of the final video. After actually producing a master, M7 whole-
episode technical, pedagogic, visual and rights QA remains mandatory.

## Future owner command sequence (not for running now)

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite init-scenes

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite \
      register-scene-plan --plan /PRIVATE/scene_plan.json

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite \
      queue-scene-stage colors-ar 1 1 --stage voice_synthesize \
      --recipe colors01_scene01_voice

After Mac worker completion (separate, owner-authorized later):

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite \
      sync-scene-stages

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite \
      approve-scene-stage colors-ar 1 1 --stage voice_synthesize \
      --sha256 EXACT_WAV_SHA --note "Owner listened to entire scene WAV"

Then same scene's LTX:

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite \
      queue-scene-stage colors-ar 1 1 --stage ltx_animate \
      --recipe colors01_scene01_ltx

Import separately produced M10 technical audio check and finally
owner-approve A2V by exact SHA:

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite \
      register-scene-audio colors-ar 1 1 --report /PRIVATE/audio_scene01.json

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite \
      approve-scene-stage colors-ar 1 1 --stage ltx_animate \
      --sha256 EXACT_MP4_SHA --note "Owner watched scene and verified lipsync"

Repeat for all scenes 2..N. View the state with:

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite \
      scene-status colors-ar 1

Then inspect full multi-scene source assembly in one trusted local
environment with access to BOTH Studio Brain DB and Mac private media:

    studio-scene-assembly --db /PRIVATE/brain.sqlite \
      --template /PRIVATE/episode_template.json \
      --series colors-ar --episode 1 \
      --voice-output-root /PRIVATE/KidsStudio/voice_outputs \
      --ltx-output-root /PRIVATE/KidsStudio/ltx_outputs

With explicit owner intent, append a new private path:
    --write-recipe /PRIVATE/KidsStudio/recipes/ep01_v1.json

The code does NOT transfer media or SQLite between Pi and Mac. Such a
trusted evidence handoff is still an operational integration item.

## Next real test and pending work

- Real installed Chatterbox and LTX-2.3 MLX wrappers must be qualified with
  the exact per-scene script, WAV and Bunny references.
- Real CUDA is not used; this is Apple Silicon MLX with GPU resource guard
  from M8, to be checked on the owner Mac.
- Test actual 2+ scene video, not just synthetic unit tests.
- Owner full human M7 QA, original/licensed music and voice/model rights,
  independent recovery backup and private-only preview remain required.
- Existing Control Center v1-v3 standalone database migration is not done.
- No merging PR #28 or user-device deployment without separate approval.

M13 CI uses synthetic WAV/MP4 bytes and mock ffprobe; success proves state
transitions and contract checks, not production video or teaching quality.
