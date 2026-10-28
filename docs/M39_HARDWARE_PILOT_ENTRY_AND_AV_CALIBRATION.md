# M39 — Honest entry gate before the first owner Mac + Raspberry Pi pilot

**Branch:** `feature/m3-series-episode-orchestrator`; draft PR #28.
**No private Mac, Pi, LLM/model inference, Google account, or YouTube contact
occurred during M39 development.** Passing GitHub CI alone never makes
hardware or language/child safety ready.

## 1. What is actually green

M38 CI exercises a complete original **two-scene software cycle** with:
SQLite Pi-like job queue → signed per-scene QA bridge → real FFmpeg WAV and
AAC-bearing MP4 → two-scene montage → M7 complete final decode → M27 final
ledger. The media are synthetic. Whisper, the independent audio/AV reviewers
and final pedagogical reviewer are **fake executable/JSON fixtures**.
The M38 run proves mechanics and SHA lineage, **not any trained model**,
rights clearance, automatic educational accuracy, authenticated Mac/Pi
transport, or YouTube upload.

## 2. M39 pass/fail audit (new)

`studio-pilot-readiness` is **read-only**. It cross-checks the current
two-scene M32 plan with the current Studio Brain database, and independently
hashes all three original script TXT files. It rejects a stale/paused
orchestrator, another queued/leased job, missing parent/scene source files
or altered SHA, and can separately check an *installed owner Mac's* M10
contract including local engine checkpoints and disk/memory. This command
does not contact Pi over TLS, execute an AI model, claim jobs, publish or
create any files.

The output provides 11 explicit gates divided by actual qualification
requirements:

| Gate | Offline test | Real-world dependency |
|---|---|---|
| LOCAL_SCENE_SOURCE_BYTES | Re-hash parent and both scene scripts | Must match pinned Pi plan |
| PI_TWO_SCENE_ORCHESTRATOR | Current plan, approved script, first voice ready | Requires current Pi SQLite |
| STUDIO_IDLE_AND_NOT_PAUSED | No queued/leased jobs, studio not paused | Avoid unrelated/old work |
| OWNER_MAC_MODEL_FILES | M10 signed/hashed files, physical prerequisites | Must run on real owner Mac |
| LIVE_PI_TLS_CLOCK | Not inferred offline | M21 fresh authenticated Pi TLS nonce + clock |
| MAC_PI_AUTHENTICATED_WORKER | Not inferred offline | Actual lease/ACK/timeouts/SHA transfer |
| REAL_VOICE_LTX_RENDER | Not inferred offline | Actual voice and video model execution |
| REAL_INDEPENDENT_AUDIO_AV_QA | Not inferred offline | Real, qualified M34/M37 models |
| RIGHTS_AND_CHILD_POLICY | Not inferred offline | Commercial rights and child-safe review |
| PRIVATE_OAUTH_UPLOAD | Only after authorized full pilot | PRIVATE-only Google OAuth |
| OWNER_POST_PRIVATE_REVIEW | Only after actual private upload | Accept, accept with notes, request edits |

**Even if every offline gate passes, the output is ONLY**
`M39_OFFLINE_PREREQUISITES_MET_LIVE_PILOT_NOT_AUTHORIZED`,
never `READY`, never a new lease, never public upload. It gives
`M21_AUTHENTICATED_LIVE_PI_PREFLIGHT` as the **next check**, not an
execution command.

Example for a later, separately authorized owner-Mac test (illustrative
private paths, **do not run until the pilot is approved**):

```sh
studio-pilot-readiness \
 --db /PRIVATE/pi_studio.sqlite \
 --plan /PRIVATE/orchestrator.json \
 --parent-script /PRIVATE/episode.txt \
 --scene-1-script /PRIVATE/scene01.txt \
 --scene-2-script /PRIVATE/scene02.txt \
 --mac-contract /PRIVATE/mac-contract.json
```

`--db` is a **local SQLite file**, not an SSH/network locator. If the
canonical DB resides on Pi, read it there or use a separately verified
snapshot only for offline analysis; a copied snapshot cannot prove the
**live** Pi stayed unchanged. Never paste passwords, OAuth tokens or HMAC
keys into diagnostics or commit checkpoint files to Git.

## 3. M39 AV-model false-PASS challenge

`studio-av-calibrate` is the new model calibration tool for future use
with **four separate, user-supplied, SHA-pinned and independently labeled**
MP4+WAV+scene-script cases:

1. `clean`: correctly synchronized, safe educational reference;
   expected `motion_sync.lip_sync=PASS`.
2. `audio_offset`: perceptible timing error;
   expected `motion_sync.lip_sync=NEEDS_FIX`.
3. `wrong_narration`: wrong spoken words/voice;
   expected `motion_sync.voice_continuity=NEEDS_FIX`.
4. `unsafe_visual`: independently established child-inappropriate visual;
   expected `visual_child_safety.no_unsafe_content=NEEDS_FIX`.

All four samples must have distinct video hashes and the manifest must
explicitly say `qualification_claimed=false`; both reviewers also have
the full label trio (`lip_sync`, `voice_continuity`, `no_unsafe_content`)
per test. Unpinned media, duplicate MP4, missing case, erased negative
label or changed model binary/checkpoint blocks the test.

By default it validates exact owner-provided bytes and calls **no** model.
Only explicit `--execute` creates sampled FFmpeg frames and passes full
sound-bearing MP4 and WAV to the two separate AV model adapters already
defined in M37. Any unconditional PASS model necessarily fails the
negative-label checks, regardless of its HMAC signatures. Results contain
per-criterion observed/expected mismatches, but do **not** become Pi M28
approvals or authorize rendering/upload.

**Crucial:** CI uses 4 synthetically distinct media hashes and
synthetic labels, NOT genuine wrong narration / unsafe visuals / visually
verified lip-sync. It proves the calibration *mechanism* rejects an
always-PASS mock; it does **not** establish trained-model skill.
Proper canary ground truth must later be created and independently
confirmed by the user or a qualified reviewer. Because the code cannot
authenticate those labels or test semantic ability, even a passed
benchmark reports `model_quality_qualified=false`.

`studio-av-calibrate --help` lists pinned model binary/checkpoint and
`--manifest` options. A private manifest sample schema for the four cases
uses the following structure for each entry (JSON shown for one case):

```json
{
  "schema_version": 1,
  "qualification_claimed": false,
  "cases": [
    {
      "case_id": "clean",
      "mp4": "/PRIVATE/clean.mp4",
      "mp4_sha256": "<64 exact hex chars>",
      "wav": "/PRIVATE/voice.wav",
      "wav_sha256": "<64 exact hex chars>",
      "script": "/PRIVATE/scene.txt",
      "script_sha256": "<64 exact hex chars>",
      "expected": {
        "motion_sync": {"lip_sync": "PASS", "voice_continuity": "PASS"},
        "visual_child_safety": {"no_unsafe_content": "PASS"}
      }
    }
  ]
}
```

The actual file **must have all four** cases with the appropriate
negative expected labels; this one-case structure is illustrative only.
Do not use real inappropriate children's footage or copyright-uncleared
media to fabricate an unsafe canary. Properly labeled safe test
alternatives and qualified oversight are required.

## 4. Exact remaining real-world blockers

The largest blocker is **real audio/AV-capable, independently calibrated
model checkpoints/adapters**. M37 accepts exact signed source evidence,
but a trusted signature only proves who made a claim, not that the
model can hear a soundtrack, understand Arabic, observe lip movements,
judge age-appropriate visuals, or respect rights. A model without these
abilities must return `UNSURE`, never self-certify success.

The second blocker is a **true first Mac↔Pi pilot**: validate actual Mac
memory/OS/disk and installed MLX wrappers, Pi clock and authenticated
worker connections, original source art, GPU performance, one WAV and
one scene clip, one bounded repair, then one complete two-scene local
MP4. No YouTube OAuth until that master passes actual quality checks.

Only then separately authorize a **single PRIVATE upload**, let the AI
operators flag quality concerns, and have the owner review that uploaded
private video with accept / accept with notes / request changes.
The Public transition always requires an entirely separate explicit
owner decision. No automated public publishing is part of M39.
