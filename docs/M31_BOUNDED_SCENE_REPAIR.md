# M31 — bounded scene repair after a negative independent AI report

**Status: development branch only; synthetic CI, no user hardware or
Google/YouTube operation.** This is NOT arbitrary self-rewriting media code.
A repair task uses a separately pre-pinned Mac recipe catalogue entry,
verified again by the Mac worker before any actual model execution.

## Why this exists

The studio must use idle workers for useful revisions rather than ask
the owner to listen to every WAV or inspect every animation. When a
scene fails the actual M28 review (UNSURE or NEEDS_FIX), repair **only
the affected stage and scene**, up to a hard limit, retaining unrelated
accepted scenes and the already accepted source voice for LTX repairs.

## Software implemented

`SceneRepair` adds two additive SQLite tables:

- `studio_scene_repair_plans`: immutable per
  series/episode/scene/stage plan containing the *current scene
  script SHA* and **one or two different alternate recipe IDs**,
  plus the SHA of a private, immutable JSON policy file.
- `studio_scene_repair_attempts`: one row per actual retry with
  previous exact Pi job and media SHA, negative model-report SHA,
  new Pi job, plan SHA, generation, and timestamp. Historical
  media receipts/reports are NEVER rewritten or erased.

`run-scene-repair-once` runs a single atomic SQLite transaction,
checks the Pi Studio Brain pause switch and current ACTIVE series,
current approved episode and immutable source script/scene hashes,
and selects **at most one** negative AI-reviewed stage.

A repair is eligible ONLY when:

1. The current scene stage is `PENDING_QA` and has an exact
   matching M28 `AI_SCENE_NEEDS_FIX` report for its **current**
   job_id, media SHA, scene script SHA and distinct model providers.
2. The original media job is actually **COMPLETED**, not LEASED,
   CANCELLED, FAILED, lost, pending, or an ambiguous upload/render.
   Its status, type, media SHA and `publication_approved=false`
   must match the exact current scene stage.
3. Voice repairs: the current M23 WAV technical receipt exists,
   and there is **NO existing LTX stage whatsoever** for the
   affected scene. This prevents invalidating a live or accepted
   downstream animation. If downstream already exists, the
   problem must be escalated and reconciled safely.
4. LTX repairs: the existing voice is **QA_APPROVED** and its
   exact SHA is retained; M10 audio-continuity evidence for
   the rejected LTX is required.
5. The next alternate recipe is different from previous recipes.
   The Mac production agent still validates it against its
   immutable local approved recipe catalogue.
6. A maximum of **TWO repair tasks** per scene/stage is allowed.
   After exhaustion, no automatic third attempt is possible.

The new job uses the **existing allowlisted** `voice_synthesize`
or `ltx_animate` payload contract (no arbitrary shell commands,
no remote path injection), unique repair idempotency request key
and a new fenced job ID. The current scene pointer transitions
to QUEUED in the same transaction. A subsequent ordinary
SceneLedger reconciliation returns it to `PENDING_QA`, where
M23/M10 and M28 must independently check the **new** media again.
Old model PASS/FAIL from an obsolete job cannot grant approval.

When no eligible failed scene exists, the scheduler takes **no action**.
It never revises an accepted scene, launches the Mac worker, downloads
models, auto-approves an episode, uploads to YouTube or publishes PUBLIC.

## Example future private repair plan

```json
{
  "schema_version": 1,
  "series_id": "colors-ar",
  "episode_number": 1,
  "scene": 2,
  "stage": "ltx_animate",
  "script_sha256": "EXACT_64_HEX_SCENE_SCRIPT_SHA256",
  "recipes": [
    "scene02_ltx_correction_v02",
    "scene02_ltx_correction_v03"
  ],
  "public_release_authorized": false
}
```

This file is only a **schema illustration**: the SHA placeholder cannot
be registered. In reality both recipe IDs must already exist on the
private Mac production station, with correct media/model pins and
actual reworked scene instructions.

## CLI (after initialized StudioQueue, SeriesManager, M13 and M28)

```sh
python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite init-scene-repair

python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
  register-scene-repair-plan --plan /PRIVATE/scene2_ltx_repairs.json

python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
  run-scene-repair-once

python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
  scene-repair-status
```

The Arabic local dashboard now shows total and currently pending
rework jobs alongside scene voice/LTX progress, and counts only
**CURRENT** M28 AI review receipts instead of stale failed
receipts from previous generations.

## Offline integration tests

M31 tests simulate Pi jobs/media with fake SHA-approved receipts and
insert **synthetic** negative M28 AI ledger records (they are NOT
outputs from live vision or audio reviewers). Tests exercise:

- exact rejected source job -> next pinned recipe, no duplicate,
  retains an unrelated already QA-approved scene;
- no repair if AI review is missing, positive, stale or from
  the wrong media/source;
- halted queue or inactive series stops every new repair;
- voice repair cannot silently invalidate an existing LTX job;
- LTX repair retains exact previously QA-approved voice digest;
- bounded two attempts, no third retry and no duplicate plan update.

The Godot/real-FFmpeg CI is general code/driver smoke, not a test of
newly rendered children's educational quality.

## What remains for one integrated hardware qualification

**M31 is a queue scheduler, not yet a self-correcting generative agent.**
New replacement recipes must currently be pre-pinned outside Git;
the AI agent does not yet write and qualify a corrected Godot/LTX
recipe from the child's safety/technical review comments.
The full no-click orchestration through script/art/rig/voice/LTX/
final assembly/M27/private upload is still incomplete. The next
software milestone should connect this bounded repair queue
to agent-proposed specific new recipes, validated against the
local Mac catalogue, and to a single truthful launch/readiness
gate. No user hardware inspection should be declared complete
until real device checks are performed.

**Safety:** no PUBLIC release permission, no automatic owner
approval, no replacement of children's safety, IP or attribution
verification with model-generated assertions. Owner's final
review of the finished YouTube PRIVATE video remains mandatory.
