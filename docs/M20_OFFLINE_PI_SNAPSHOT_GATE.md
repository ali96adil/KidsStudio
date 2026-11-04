# M20 — Offline Studio Brain M13 → Mac M19 gate (code-only)

**Development status:** Draft PR #28, unmerged. Nothing is installed,
run, migrated, synchronized or published on the owner Mac/Pi. CI inputs
are synthetic and private to disposable Linux test runners.

## Why a new gate exists

M19 compared an M13-shaped local scene-plan JSON to the Mac-approved
two-scene scripts and voice recipes. An arbitrary JSON file could look
correct without having been registered in Studio Brain. M20 adds a
**read-only cross-check against an exact independently pinned M13 SQLite
backup**, tied to the *same* M19 plan SHA and both Mac scene script SHA values.

This checks real Studio Brain **schema, state and audit relationships** in
a coherent database snapshot; it does not attest that an arbitrary
user-supplied snapshot truly came from the owner's Pi, nor that the live
Pi has not changed since it was captured.

## What is checked

1. M19 still passes first: exact Mac contract, original parent script,
   two distinct approved scene files, and two pinned voice-only recipes.
2. An **existing, privately supplied**, absolute, non-symlink,
   250 MB maximum, standalone SQLite `.sqlite` or `.db` file resides
   below the owner's primary approved private Mac root. Its exact
   SHA256 must be supplied separately. Any adjacent `-wal`, `-shm`
   or `-journal` file blocks the checker. A live WAL database must NOT
   be passed to SQLite `immutable=1`.
3. SQLite `integrity_check` and `foreign_key_check` pass; M13 tables exist.
   The reader opens `mode=ro&immutable=1` with `query_only=ON`, and
   checks snapshot SHA again afterwards. No write transaction, migration,
   media run or network access occurs.
4. Exactly one active series; the target episode remains
   `SCRIPT_APPROVED`, its parent script SHA matches M19, the owner note
   is present and the Studio Brain `SCRIPT_APPROVED_BY_OWNER` audit
   action exists.
5. M13 `studio_scene_plans` contains the *exact* owner-recorded scene
   plan file SHA and parent script SHA. Exactly two consecutive
   `studio_scenes` records match the plan's order, SHA256 and objective.
6. There are no existing `studio_scene_stages` for that episode: this is
   an **initial voice pilot** gate, not permission to duplicate work in
   progress or retry an uncertain model execution.

If all pass, result is:
`OFFLINE_M13_SNAPSHOT_MATCH_NOT_LIVE_PI_ATTESTED`.
Its flags explicitly state:
`offline_scene_records_match=true`,
`live_pi_state_verified=false`,
`snapshot_freshness_verified=false` and
`publication_approved=false`.

## Future owner-authorized use (paths are placeholders)

First, make a consistent SQLite backup with the existing **M9 SQLite
online backup API** on the database host, in an owner-private folder
outside Git. Copy the *closed* backup by a secure trusted means to an
approved private Mac directory. Obtain its SHA256 from its exact copied
bytes. Never copy a live `.sqlite` without checking its WAL state, and
do not run this gate on the production DB directly.

```bash
studio-m13-snapshot-gate \
  --mac-contract /PRIVATE/KidsStudio/mac_contract.json \
  --scene-plan /PRIVATE/KidsStudio/scene_plan.json \
  --scene-plan-sha256 EXACT_REGISTERED_M13_PLAN_SHA256 \
  --scene-1-script /PRIVATE/KidsStudio/scripts/scene01.txt \
  --scene-1-voice-recipe /PRIVATE/KidsStudio/recipes/scene01_voice.json \
  --scene-2-script /PRIVATE/KidsStudio/scripts/scene02.txt \
  --scene-2-voice-recipe /PRIVATE/KidsStudio/recipes/scene02_voice.json \
  --pi-snapshot /PRIVATE/KidsStudio/snapshots/m13_snapshot.sqlite \
  --pi-snapshot-sha256 EXACT_SNAPSHOT_SHA256
```

This command does not exist on the owner's machine unless the repository
branch is separately installed later with the owner's authorization.
Outputs are metadata only, with no paths, SQLite rows, scripts or keys
exposed. Failures return a redacted class name.

## Synthetic CI and limitations

The CI tests use the real StudioQueue, SeriesManager and SceneLedger
schema, create a registered two-scene plan and a SQLite online backup,
then verify the snapshot against synthetic Mac M19 assets. They reject
SHA changes, a re-pinned altered scene objective, absent owner audit,
previously queued voice work and standalone snapshot WAL sidecars.
These are synthetic test fixtures. They cannot attest to the live Pi
or real owner approvals.

**Not yet verified:** that any real snapshot came from the owner's
Raspberry Pi, that the Pi state is still current, that Mac Chatterbox or
LTX-2.3 MLX APIs work, that voices and generated art are legal/approved,
the two real audio/video scenes, private media backup restore, the 11
substantive M7 human quality checks, and YouTube publishing.

A later device acceptance must authenticate current Pi state, confirm
snapshot freshness, and run an explicit time/lease preflight before
allowing even a single real model invocation. This gate does not and
cannot authorize paid APIs or publication.
