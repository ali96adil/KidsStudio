# M4 — Episode assembly and Bunny v07 pipeline

**Status:** development on a draft GitHub branch, NOT installed on the Mac/Pi.
No GPU inference, remote AI API calls, subscriptions, uploads or publishing.

## What is implemented

1. Series Manager stores exact owner-approved script SHA256.
2. Owner queues a dedicated episode_assemble media request that includes this
   script SHA and one approved Mac-local recipe identifier.
3. Pi coordinator only leases it to the separately enrolled Mac media worker.
4. Mac worker verifies the private outer recipe SHA, episode recipe, original
   script SHA, input videos, face-scripts v06/v07, and approved paths.
5. Bunny front-facing 384x384 clips explicitly marked bunny_v07 run through
   v06 -> v07. Other clips are not face-retouched.
6. Scene video and embedded audio are normalized to 1280x720, 24fps,
   H.264/AAC and concatenated with FFmpeg into a private QA master.
7. ffprobe verifies one audio + one video track, geometry and duration bounds.
8. Mac-local journal prevents blind retry after uncertain rendering.
9. Pi stores only output SHA256, bytes and status. Human QA is mandatory.
10. A failed/changed hash blocks the job, never authorizes publication.

## Not yet implemented

- Generating NEW Chatterbox audio or LTX A2V from a new script. This phase
  consumes previously rendered, pinned local media with embedded audio.
- Using Bunny v07 on arbitrary aspect ratios, body poses or characters.
- Automated lip-sync quality, child pedagogy, language, fact/rights QA.
- Real human proof of voice commercial license, or YouTube upload/publishing.
- Migration of earlier standalone Control Center v1-v3 into Studio Brain DB.

The voice_rights field is an owner's declaration, not verified licensing.
All result statuses are for INTERNAL review; public release remains blocked.

## Private recipe example (do NOT commit real paths, media or keys)

Mac media worker catalog:
    {
      "schema_version": 1,
      "recipes": {
        "bunny_colors_ep01": {
          "kind": "episode_assemble",
          "output_root": "/PRIVATE/KidsStudio/runs",
          "inputs": {
            "episode_recipe": "/PRIVATE/KidsStudio/recipes/ep01.json"
          },
          "sha256": {
            "episode_recipe": "EXACT_64_HEX_SHA256"
          }
        }
      }
    }

Episode recipe:
    {
      "schema_version": 1,
      "series_id": "colors-ar",
      "episode_number": 1,
      "private_root": "/PRIVATE/KidsStudio",
      "output_root": "/PRIVATE/KidsStudio/runs",
      "voice_rights": "INTERNAL_TEST_ONLY",
      "script": {
        "path": "/PRIVATE/KidsStudio/scripts/ep01.txt",
        "sha256": "EXACT_64_HEX_SHA256"
      },
      "tools": {
        "ffmpeg": "/path/to/ffmpeg",
        "ffprobe": "/path/to/ffprobe",
        "face_python": "/PRIVATE/KidsStudio/venv/bin/python",
        "face_v06": "/PRIVATE/KidsStudio/agents/kidsstudio_bunny_face_refine_v06.py",
        "face_v06_sha256": "EXACT_64_HEX_SHA256",
        "face_v07": "/PRIVATE/KidsStudio/agents/kidsstudio_bunny_face_cleanup_v07.py",
        "face_v07_sha256": "EXACT_64_HEX_SHA256"
      },
      "clips": [
        {
          "video": "/PRIVATE/KidsStudio/ltx/scene_01.mp4",
          "sha256": "EXACT_64_HEX_SHA256",
          "face_cleanup": "bunny_v07"
        }
      ]
    }

These examples are not runnable; paths and hashes must be pinned and verified
on the owner's Mac when device deployment is authorized.

## Future one-shot usage (not for running now)

Read-only source preflight:

    python -m kidsstudio.episode_assembly \
      --recipe /PRIVATE/KidsStudio/recipes/ep01.json --preflight

Locally approved test assembly requires an explicit --execute and a unique
--run-id. Pi-coordinated runs instead use the existing secured media worker
and a durable journal, naming the immutable run by queue job ID.

Owner queues the already approved script:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
      queue-render colors-ar 1 --media-kind episode_assemble \
      --recipe bunny_colors_ep01

## Tests and acceptance boundaries

Offline tests use fake media executors plus real queue, coordinator, journal,
recipe hash checks and Series Manager. They cover immutable run directories,
script mismatch, changed recipe, unauthorized completion endpoints and QA gate.
They do not represent real Mac Chatterbox/LTX production, lip-sync, sound,
rights, or artistic quality checks.

The later end-to-end acceptance requires a full real episode rendered, listened
to and visually checked on the owner Mac, and an explicit rights review.
