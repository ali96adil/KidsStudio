# M5 — Single-source dashboard + Chatterbox/LTX source onboarding

**Development code only.** Not installed or started on the owner's Mac/Pi.
No provider calls, Chatterbox inference, LTX inference, GPU jobs,
model downloads, upload, social scheduling or public publishing are performed.

## 1. Real control-center dashboard

The new read-only studio-dashboard server derives its data from the existing
StudioQueue SQLite database and the SeriesManager tables in the SAME DB:

- Per-series curriculum coverage and approved/total episode counts
- Script written/reviewed/ready for production, media queue, rendered QA and
  owner-approved states
- Queue counts: QUEUED, LEASED, COMPLETED, FAILED and CANCELLED
- Owner notes and series-specific milestones
- Stage timeline: curriculum, writing, editorial review, voice, LTX A2V,
  face cleanup, montage, final QA

**Critical truth condition:** until the TTS/LTX/face execution workers have
separate, authoritative receipts, those three timeline stages always display
NOT_TRACKED, even if a composite MP4 was rendered. This prevents false claims
about voice or lip-sync quality and resists confusing a queue receipt with
a published video.

The service listens ONLY on IPv4 loopback (127.0.0.1), refuses unexpected Host
headers, serves only fixed packaged assets, disables query strings and mutation
routes, sends restrictive CSP/no-store headers, and has no database write API.
It does not expose original scripts, paths, job payloads, model keys or queue
result records. For now owner notes are changed via the local series_cli.

Once all phases are ready and owner approves a device test:

    studio-dashboard --db /PRIVATE/studio.sqlite --port 8793

Open http://127.0.0.1:8793 on the SAME host. This is not a cloud dashboard,
not remote access, and not a deployed web app. Packaging includes the HTML,
CSS and JavaScript as package-data.

## 2. Previously created Chatterbox and LTX source intake

A new local-only studio-source-preflight CLI verifies an owner-supplied PRIVATE
manifest of scene audio + generated A2V media. It checks:

- Exact approved script SHA256 and explicit Arabic/English language
- Per-scene Chatterbox WAV SHA256, numbered 1..N scenes
- Per-scene LTX MP4 SHA256 with declared source voice WAV SHA256
- ffprobe presence of one audio channel in WAV; one video and one audio stream
  inside A2V clips; bounded scene duration
- Bunny v07 cleanup permitted only for 384x384 source video
- Pinned v06 and v07 Python tool files; all paths confined to the private root
- Immutable, owner-reviewed manifest and EXCLUSIVE creation of a private
  assembly recipe, never overwriting previous recipes

This DOES NOT run Chatterbox or LTX. It DOES NOT prove the sound inside the
MP4 equals the WAV sample or that the Bunny actually speaks convincingly.
Voice license remains DECLARED, not independently verified. Its output status
is MEDIA_SOURCES_PROBED_AWAITING_OWNER_QA.

With real approved Mac files in the future, a local private manifest contains:

    {
      "schema_version":1,
      "series_id":"colors-ar",
      "episode_number":1,
      "language":"ar",
      "private_root":"/PRIVATE/KidsStudio",
      "output_root":"/PRIVATE/KidsStudio/renders",
      "voice_rights":"INTERNAL_TEST_ONLY",
      "script":{
        "path":"/PRIVATE/KidsStudio/scripts/colors_ep01.txt",
        "sha256":"EXACT_64_HEX_SHA256"
      },
      "tools":{
        "ffmpeg":"/path/to/ffmpeg",
        "ffprobe":"/path/to/ffprobe",
        "face_python":"/PRIVATE/KidsStudio/venv/bin/python",
        "face_v06":"/PRIVATE/KidsStudio/agents/kidsstudio_bunny_face_refine_v06.py",
        "face_v06_sha256":"EXACT_64_HEX_SHA256",
        "face_v07":"/PRIVATE/KidsStudio/agents/kidsstudio_bunny_face_cleanup_v07.py",
        "face_v07_sha256":"EXACT_64_HEX_SHA256"
      },
      "scenes":[{
        "scene":1,
        "voice_wav":"/PRIVATE/KidsStudio/voice/scene01.wav",
        "voice_sha256":"EXACT_64_HEX_SHA256",
        "ltx_video":"/PRIVATE/KidsStudio/ltx/scene01.mp4",
        "ltx_sha256":"EXACT_64_HEX_SHA256",
        "source_voice_sha256":"SAME_VOICE_SHA256",
        "face_cleanup":"bunny_v07"
      }]
    }

Paths and hashes are placeholders, not instructions to run on the Mac now.
A future read-only check is:

    studio-source-preflight --plan /PRIVATE/source_plan.json

After owner inspection, a new private assembly recipe can be generated with:

    studio-source-preflight --plan /PRIVATE/source_plan.json \
      --write-assembly-recipe /PRIVATE/KidsStudio/recipes/colors_01.json

That output is NOT automatically an approved MediaRecipes entry. The existing
Pi-to-Mac media worker only accepts manually pinned approved recipes.

## Outstanding before end-to-end acceptance

- Confirm actual Chatterbox command contract and LTX MLX a2v CLI, versions,
  pinned model weights, voice references and available memory on owner Mac.
- Build purpose-specific, no-shell-injection Mac voice and A2V workers with
  durable journals, local resource limits, bounded retries and exact source
  hashes; connect their receipts to the dashboard timeline.
- Add objective quality metrics + human lip-sync, artistic, voice and child
  pedagogy gates; verify commercial rights and proper archiving.
- Replace / migrate previous standalone Control Center v1–v3 DB after
  explicit owner review; do not silently merge schemas or overwrite data.
- End-to-end full episode test in Mac environment, after code-phase completion.
