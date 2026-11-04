# M33 — actual Pi/Mac voice authorization bridge + bounded local production cycle

**Implementation branch:** `feature/m3-series-episode-orchestrator`, PR #28 (DRAFT).
**No actual user Mac/Pi changes, models downloaded/invoked, media rendered or YouTube uploads.**
M33 verifies and connects production *software contracts*, not live quality.

## Critical integration fix

The M30 script reviewers can internally set `SCRIPT_APPROVED` with
`M30_TWO_INDEPENDENT_AI_INTERNAL_PRIVATE_ONLY`; M32 will then queue a
two-scene first-voice pilot without an owner script sign-off.

Before M33 the existing M21 read-only `pilot-readiness` and M22
authenticated `pilot-voice-lease-check` **still required**
`SCRIPT_APPROVED_BY_OWNER`, so the queued task was rejected by the
real Mac worker even when the independent AI gate was current.
This was a real broken production handoff, not a cosmetic issue.

The new `kidsstudio/script_gate.py` implements ONE current-script
predicate shared by both Pi checks, allowing exactly:
1. The legacy script-owner audit for a current active script, or
2. A current M30 independent QA receipt for the exact episode
   revision, draft job ID, source SHA, distinct reviewer IDs,
   complete SHA-pinned review records and the corresponding AI
   audit; **no owner audit is manufactured** and a note alone is
   insufficient.

The existing Pi lease fencing, worker identity, TLS bearer token,
heartbeat, pause control, exact recipe/source/scene SHA and
single-first-scene restrictions remain unchanged. The Pi lease
response now also carries the `server_time` required by the existing
Mac media worker verification.

`tests/test_ai_pilot_bridge_m33.py` verifies this contract via the
actual Coordinator dispatch and a **real localhost HTTPS server with
ephemeral certificate and RemoteClient**, using entirely synthetic
model/script data. Stale episode revision, revoked M30 review, wrong
scene plan SHA, paused Pi and unknown worker IDs are denied.
It does NOT run actual voice synthesis.

## Production-cycle driver

The new `studio-cycle` command is a safe **single local invocation**.
By default it is **read-only**:

```sh
studio-cycle --db /PRIVATE/studio.sqlite \
  --plan /PRIVATE/episode01_orchestration.json
```

An operator may explicitly permit bounded state transitions:

```sh
studio-cycle --db /PRIVATE/studio.sqlite \
  --plan /PRIVATE/episode01_orchestration.json \
  --steps 8 --execute
```

Each step uses the immutable M32 plan and EXACT matching episode
sources and only does **ONE** authorized local state transition:

- Reconcile a completed/failed/cancelled Mac media job already
  recorded in the Pi queue, **scoped to the current episode**;
- Reconcile a returned final `episode_assemble` job using the
  existing `SeriesManager` validity rules;
- Auto-approve an individual scene only when the matching M28
  independent QA **has already been registered and fully verified**
  against the current SHA-pinned M23 WAV or M10 audio evidence.
  This command never signs an M28 report or invents an AI PASS;
- Queue one M32/M31-allowed next job or bounded correction using
  approved private recipe IDs and the existing queue pause/lease
  guards;
- Transition completed master from `RENDERED_QA_PENDING` to the
  internal `EPISODE_APPROVED` **only if M7+M27 already contain
  current full final-video AI QA**. This still means **PRIVATE-only
  readiness**, not post-upload owner approval.

A bounded call stops immediately on any newly queued Mac/GPU job,
missing real tech/AI review, changed plan, new owner dependency,
or completed internal approval. It never busy-waits, starts a server,
polls indefinitely, executes an external process, sends a prompt,
uploads video, or changes YouTube visibility.
There are no external worker invocations inside this module; existing
authenticated Mac media workers remain independent processes.

## Explicit blockers shown to the operator

The status exposes one of:
- `MAC_MEDIA_WORKER_OR_JOB_ACK_REQUIRED`;
- `CURRENT_SCENE_RECEIPT_AWAITING_RECONCILIATION`;
- `M23_M10_AND_TRUSTED_AI_SCENE_REVIEW_REQUIRED`;
- `SIGNED_AI_SCENE_REVIEW_ALREADY_RECORDED`;
- `SCENE_REPAIR_PENDING`;
- `MAC_FINAL_ASSEMBLY_WORKER_REQUIRED`;
- `M7_M27_INDEPENDENT_FINAL_VIDEO_QA_REQUIRED`;
- `AWAIT_SEPARATE_PRIVATE_UPLOAD_POLICY_AND_OWNER_REVIEW`.

It always reports `mac_pi_hardware_test_ready=false`,
`real_media_production_qualified=false`,
`private_upload_permitted_by_this_tool=false`, and
`public_release_authorized=false`.

## What GitHub CI proves

`tests/test_studio_cycle_m33.py` runs the **synthetic** software
pipeline across two scenes: current script → first voice task →
Pi media receipt → Pi stage reconciliation → already-registered
independent scene QA → LTX task → second scene → final montage job
→ final-episode receipt → **wait** for M7/M27 external review.

The model/voice/video receipts are deliberately fake fixtures;
a test's simulated M28 PASS is NOT a real model decision.
CI also tests that a stale positive QA receipt without matching
technical media proof cannot be consumed, and that a paused
coordinator or altered scene plan dispatches no jobs.

## Remaining cut before ONE real hardware qualification

**Not ready for unattended end-to-end production.** Software still
needs a trustworthy operational pipeline to generate/import actual
model-based audio QA (with genuine sound listening), independently
review actual frame/video motion, create and qualify corrected
Mac-local recipes from failed AI reviews, and autonomously generate
full educational scene plans/assets. M33's current Mac worker daemon
and Pi coordinator must be configured with real user devices and
tested against the available model checkpoints, after the software
qualification suite passes.

When that is implemented, perform ONE integrated Mac/Pi pilot with
external upload disabled, then separately authorize private YouTube
OAuth and the **owner's final review of the uploaded PRIVATE video**.
No PUBLIC operation is included anywhere in M33.
