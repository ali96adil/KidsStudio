# M8 — Engine Qualification, Cooperative Compute Gate and Private Preview Readiness

Status: DEVELOPMENT CODE ON DRAFT GITHUB PR ONLY. Nothing has been deployed,
installed, rendered or published on the owner's Mac/Pi. No model, paid API,
voice service or YouTube service was invoked.

## A. Engine checkpoint qualification

The local studio-engine-qualify command inspects an owner-pinned PRIVATE
manifest and requires platform Darwin on Apple Silicon, a declared minimum
physical memory level, network_required=false, and SHA256 hashes for 1–16
model checkpoints inside the private asset root. Engine identifiers are
chatterbox_multilingual_mlx or ltx_2_3_mlx, matched to stage kind. Reject
wrong/missing/model files, mutated hashes, symlink inputs, non-Mac platforms,
insufficient memory and manifest ambiguity.

The actual local StagePlan.run launch refuses to execute the real Python
adapter unless checkpoint qualification passes. Synthetic CI test adapters
remain injected and do not synthesize or animate media.

A qualified checkpoint report is NOT evidence that the actual Chatterbox/LTX
Python API, Mac wrapper, licensing, voice identity, pronunciation, lip sync
or model output are correct. These still require the owner Mac final test.

Example private engine manifest:

    {
      "schema_version":1,
      "kind":"ltx_animate",
      "engine":"ltx_2_3_mlx",
      "platform":"Darwin",
      "arch":"arm64",
      "minimum_memory_gib":32,
      "network_required":false,
      "checkpoints":[{
        "role":"main","path":"/PRIVATE/KidsStudio/models/ltx.safetensors",
        "sha256":"EXACT_64_CHARACTER_LOWERCASE_SHA256"
      }]
    }

Future read-only command only after an owner-approved installation:

    studio-engine-qualify \
      --manifest /PRIVATE/KidsStudio/ltx_qualified.json \
      --private-root /PRIVATE/KidsStudio --kind ltx_animate

## B. Cooperative compute reservation

KidsStudio workers share one advisory lock in their private root. Voice,
LTX, episode assembly, and Godot/character rendering via the Mac MediaExecutor
use this reservation before expensive work. Recipes must share the SAME
private root. This does NOT stop unrelated ComfyUI, Final Cut or third-party
processes; it is not a system-wide GPU scheduler. Worker leases and heartbeat
operate through the existing Pi coordinator.

## C. Immutable private archives

The offline studio-archive tool reads a private JSON archive plan with:
schema_version, series_id, episode_number, archive_id, private_root,
archive_root, items. Each item has role, absolute path, SHA256. Required roles
are episode_master, approved_script, technical_qa and owner_qa. Optional
roles include voice_master, a2v_master, scene_manifest, thumbnail, subtitles,
production_notes and coloring_page.

The archive is created in a NEW restricted folder, never overwriting prior
runs. The tool checks source SHA before and after copying, checks copied
bytes, writes a final private manifest with roles and SHA256 (not original
source paths), and verifies full archive integrity. Partial failures are
retained for manual inspection; they are not reported as verified.

Archive is one extra copy ON THE SAME DISK by default, not a substitute for
an independent offline/encrypted backup and a tested restore. No cloud
sync or backup is enabled automatically.

Future commands only after owner authorizes installation and supplies
verified private paths:

    studio-archive --plan /PRIVATE/archive_plan.json
    studio-archive --plan /PRIVATE/archive_plan.json --create
    studio-archive --verify /PRIVATE/KidsStudio/archives/colors-ar/ep001/ep01-v1

## D. Explicit private-upload readiness, no uploader

A separate studio-private-readiness command verifies the same Studio Brain
SQLite database AND a finalized archive. It requires one EPISODE_APPROVED
episode, current completed private render receipt and SHA, matching M7
technical + human QA (11 criteria), and exact archived copies of the MP4,
script, technical report and owner review. If a voice/LTX stage was started,
both independent owner approvals must be recorded.

Success status is READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED. It performs
NO upload, and public release is not authorized. The owner still decides
whether and when to upload PRIVATELY, review, then later publish.

Future command (the archive and Studio Brain DB must be locally available):

    studio-private-readiness --db /PRIVATE/studio.sqlite \
      --archive /PRIVATE/archives/colors-ar/ep001/ep01-v1 \
      --series colors-ar --episode 1

If Studio Brain is on Pi and original media is on Mac, a separate secure
evidence transfer is needed. M8 never copies original media to Pi or Git.

## Outstanding final acceptance and operational dependencies

- Verify real Chatterbox multilingual MLX wrapper and Bunny voice B preset.
- Verify real LTX 2.3 MLX adapter, checkpoint weights and full Mac workflow.
- Verify copyright, commercial model/voice rights, music and sound FX licenses.
- Build full episode with production WAV, A2V and face review on owner Mac.
- Apply M7 QA and human review to the real final episode, not synthetic CI.
- Validate a separate recovery backup and restore.
- Explicitly reconcile prior standalone Control Center v1-v3 data, if needed.
- Preview on YouTube as PRIVATE only with owner's approval; public release
  requires a separate subsequent authorization.

CI synthetic test success proves implementation contracts, not live Mac
production, human artistic judgment, educational value or platform approval.
