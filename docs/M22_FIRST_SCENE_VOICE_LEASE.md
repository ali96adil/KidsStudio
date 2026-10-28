# M22 — One-scene voice pilot: one owner queue + live lease recheck

**Status:** GitHub PR #28 only, still DRAFT/unmerged. No installation,
model run, voice/audio generation, Pi/Mac network access, API expenditure,
private media transfer or YouTube upload on the owner's actual devices.
CI uses a disposable SQLite Pi, local fake voice engine and fake client.

## Why this exists

M21 proves that the two-scene M13 plan matches a live authenticated Pi
observation **at that moment**, and explicitly does not grant authority
to start an engine. Between that check and an eventual Mac worker claim,
the owner could pause the series, cancel an attempt, revise scene data
or someone might already have initiated the first voice stage.

M22 intentionally does **not** treat a copied M21 JSON status as an
execution token. The authoritative Pi database is rechecked at queue
time (within an atomic SQLite write transaction), and a SECOND time
against the **particular active job lease** immediately before the
Mac worker's one-shot model call. An owner still needs to separately
authorize/execute a worker on the actual machine.

## 1. Owner queues only scene 1

The new owner CLI command:

```sh
python -m kidsstudio.series_cli --db /PRIVATE/pi-brain.sqlite \
  queue-first-voice-pilot colors-ar 1 \
  --recipe m22_voice_scene01 \
  --plan-sha256 EXACT_REGISTERED_M13_SCENE_PLAN_SHA \
  --owner-note "Owner reviewed current Pi and approved a single first-scene voice trial."
```

This is **not a command to run now**. It will enqueue work only in the
future, after the owner has verified the real Mac/Pi state and chosen the
correct installed recipe, stage rights and engine. No model is executed
by the command itself.

One `BEGIN IMMEDIATE` transaction checks active/unpaused series,
approved parent script, owner review note/audit, exact M13 plan SHA,
**exactly two ordered scenes**, no previous scene-stage records, and
a nonempty substantive owner note. It atomically creates only the
scene-1 `voice_synthesize` job, with bounded SHA-pinned payload
`{recipe_id, script_sha256, pilot_scene: 1, pilot_plan_sha256}`,
a single maximum lease attempt, the matching scene-stage row, and
owner audit note. No scene 2 or LTX job is queued.

Duplicate clicks and re-enqueue after a failed/cancelled attempt are
blocked: M13 scene-stage records are never silently overwritten.

## 2. Recheck the specific leased job before model start

The existing HTTPS coordinator exposes
`POST /v1/pilot-voice-lease-check`, requiring the *same authenticated
worker* with explicit `voice_synthesize` permission. Only the
currently LEASED job and generation may be checked.

The Pi compares (read-only, within a SQLite transaction):

- job ID, generation, worker identity, lease expiry, kind and full payload;
- exact local recipe identifier, plan SHA, script SHA and scene number 1;
- episode's current approved parent state, active series and review/audit;
- registered M13 scene plan and per-scene script, with the job bound to
  exactly one matching current `studio_scene_stages` record;
- coordinator not paused and no additional stage jobs on this episode.

The Pi responds only with the exact validated metadata and
`model_execution_authorized: false`. The worker refuses altered,
partial or unexpected replies. The first check must pass **before
MediaJournal.STARTED**. The Mac then reserves its immutable STARTED
journal record, and repeats the **same live lease check immediately
before calling the local executor**. A failure on this second check
leaves the attempt permanently quarantined, never silently retried,
and **no model is called**.

This applies to the new `pilot_scene` job payload; the existing
non-pilot legacy stage protocol is not silently expanded. After a
successful proof, the usual Mac MediaJournal prevents re-rendering
the same job after a crash or lost completion acknowledgment.

## Test coverage

Synthetic tests verify successful single-scene fake voice completion
with one and only one fake executor invocation, wrong plan SHA,
double enqueue, changed Pi plan after claim, revoked lease,
coordinator/series pause, maliciously changed proof response and
empty Mac execution journal on an initial rejected lease, and a
STARTED quarantine with zero fake model calls if the owner pauses
between the journal reservation and the second proof. No Chatterbox or
LTX MLX inference is invoked by CI.

## Important boundaries

This is an **at-most-one-start attempt**, NOT evidence of valid
speech, artistic quality, commercial licensing or publication rights.
The Pi validates a point-in-time lease immediately before execution;
it cannot prevent a later cancellation during a long-running GPU
inference without a stronger integrated cancellation/heartbeat
coordinator. There remains a small distributed time-of-check/time-of-use
interval between remote proof and starting the local executor.

The single-use owner CLI is not proof that an M21 live preflight report
was cryptographically bound to the queue request; only the current
Pi state and exact registered plan matter at the M22 transaction.
The real-device trial must still explicitly check M19–M21 and stage
rights/wrapper compatibility, then use M22 on the same reviewed recipe.

M22 does not start a background service, authorize an owner device,
approve the generated WAV, launch LTX, guarantee Pi/Mac time
synchronization beyond existing client clock checks, or publish.
Only after a real owner-reviewed WAV can the subsequent scene 2
and LTX paths be assessed, each with its own explicit approvals.
