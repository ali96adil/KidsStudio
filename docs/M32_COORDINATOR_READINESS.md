# M32 — Coordinated one-job production scheduler and honest readiness gate

**Branch:** `feature/m3-series-episode-orchestrator` / draft PR #28.
**Status:** new conservative software scheduler, **NOT** a finished
autonomous studio or a qualified Mac/Pi release. No production hardware
or YouTube credentials have been touched.

## Scope and safe behavior

`studio-orchestrator` exposes `init`, `pin`, `status`, and `tick`.
It joins current Studio Brain SQLite series, M13 scene manifests, M30
independent script approval, M31 bounded retries, and existing
`SceneLedger`/`SeriesManager` queue methods.

- `status` is **read-only**: it inspects current episode/scene state,
  matching pinned source script SHA and scene plan SHA, current staged
  WAV/LTX statuses and next permitted action. It NEVER generates a
  success report for hardware or YouTube.
- `pin` registers one **immutable**, privately stored JSON scheduling
  plan for the exact series/episode. It must match all actual scene
  scripts, scene count, approved parent episode and frozen M13
  scene-plan SHA. Every scene has separate, pre-approved Mac-local
  voice and LTX recipe identifiers, and assembly has an exact Mac
  catalogue SHA. A plan cannot be changed without a separate
  revision/migration workflow.
- `tick` can queue **at most one** safe job. It does not execute
  any task or call models, Mac, Pi worker, YouTube or any external
  network. It re-reads the private plan, compares its SHA to the
  status just observed, respects queue pause, and calls the
  independently guarded existing queue method:
  1. First scene WAV only when a current **two-provider M30 script
     approval** is present; the legacy owner-approval path alone does
     not manufacture AI authorization.
  2. Next LTX only after the corresponding WAV is `QA_APPROVED`.
  3. Later scenes start sequentially only after the previous scene's
     LTX is `QA_APPROVED`.
  4. Negative **current** M28 AI evidence, with matching M23/M10 SHA
     and pre-pinned eligible M31 repair plan, may queue at most one
     scoped replacement recipe. Accepted, stale or unrelated scenes
     cannot be re-run by this repair path.
  5. After every scene has a voice and LTX `QA_APPROVED` current
     receipt, queue the exact catalogue-bound `episode_assemble`
     job using the existing M13/M14/M16 guards.

It never skips WAV technical checks, voice rights evidence, M10 audio
continuity, signed multimodal QA, M27 final-episode QA, M25/M26
private-upload policy or M24 owner post-PRIVATE review.
`tick` does **not** automatically perform these specialist reviews
or call an external media worker. Those remain separate agents.

The Studio Dashboard is a **read-only observer**. M32 displays whether
a pinned orchestration plan exists and its stored script SHA still
matches. The Dashboard cannot check a private JSON file that it
has not been given, so it explicitly says the plan file still needs
local verification. It always says hardware is not yet qualified.

## Example immutable plan (SHA placeholders must be real to register)

```json
{
  "schema_version": 1,
  "series_id": "colors-ar",
  "episode_number": 1,
  "script_sha256": "EXACT_PARENT_SCRIPT_SHA256",
  "scene_plan_sha256": "EXACT_FROZEN_SCENE_PLAN_SHA256",
  "scenes": [
    {
      "scene": 1,
      "script_sha256": "EXACT_SCENE_1_SHA256",
      "voice_recipe": "scene1_voice",
      "ltx_recipe": "scene1_ltx"
    },
    {
      "scene": 2,
      "script_sha256": "EXACT_SCENE_2_SHA256",
      "voice_recipe": "scene2_voice",
      "ltx_recipe": "scene2_ltx"
    }
  ],
  "assembly": {
    "recipe_id": "scene_assembly",
    "catalogue_sha256": "EXACT_MAC_PRIVATE_CATALOGUE_SHA256"
  },
  "public_release_authorized": false
}
```

```sh
studio-orchestrator --db /PRIVATE/studio.sqlite init
studio-orchestrator --db /PRIVATE/studio.sqlite \
  --plan /PRIVATE/episode01_orchestration.json pin

# No writes, no model calls, no upload:
studio-orchestrator --db /PRIVATE/studio.sqlite \
  --plan /PRIVATE/episode01_orchestration.json status

# Explicitly enqueue at most one safe job per invocation:
studio-orchestrator --db /PRIVATE/studio.sqlite \
  --plan /PRIVATE/episode01_orchestration.json tick
```

A real control loop will later call tick, lease one job from Pi to
the permitted Mac producer, collect an actual result, run technical
checks and trusted AI reviewers, and iterate. **That worker loop is
not yet in this M32 change**, so this milestone must not be described
as unattended end-to-end production. The plan still requires recipes
pre-pinned on Mac; no AI-generated unreviewed recipe mutations.

## Entry gate before owner device checks

The M32 status contains the following unconditional, truthful flags:

```json
{
  "software_full_cycle_qualified": false,
  "mac_pi_hardware_test_ready": false,
  "youtube_private_upload_qualified": false,
  "owner_final_video_review_required": true,
  "public_release_authorized": false
}
```

**Why not READY?** There is still no proven unattended full-cycle
production run that uses authentic independent Arabic speech and
audio/vision inference, verifies rights, resolves image/animation
production dependencies, and creates an original complete video
without manual per-scene setup. No real Mac/Pi remote job transfer
or private YouTube OAuth exercise has been performed either.

The safe next software milestone is a **fully synthetic acceptance
harness** that wires the Pi producer and Mac worker state transitions,
AI review receipts, bounded regeneration, assembly, exact final master
and post-PRIVATE owner workflow as fake external operations, plus
honest blockers. When that is green and real model adapters and
media recipes are connected, run **one integrated Mac/Pi pilot with
external upload disabled**, followed by a separately authorized
real PRIVATE upload and owner review.

## CI scope

`tests/test_studio_orchestrator_m32.py` walks two synthetic
scenes from independently reviewed script → first voice → approved
LTX → second voice → second LTX → queued final assembly.
It verifies one job/tick, paused queue, immutable private plan,
rejecting legacy owner approval as AI proof, mock rejected WAV
repair via scoped M31, source/plan mismatch, and flags remaining
unqualified. These are **not real educational video production**:
all media receipts, human listening and AI tests are synthetic
fixtures. General Godot smoke remains a separate real engine test.

No PUBLIC publishing action, automatic approval of a private
YouTube video, or external/private media upload exists in M32.
