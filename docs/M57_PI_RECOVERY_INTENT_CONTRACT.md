# M57 — Pi intake of a fresh M56 montage-recovery proposal

**Status:** Development-only draft PR #28. No owner devices, real model/FFmpeg
workload, media transfer, YouTube OAuth, upload or main branch updates.

## What changes

M56 prepares an immutable private proposal on Mac: each ordered scene
either references an approved original LTX source or proposes a recovered
normalized candidate which *Mac-side* M7 full decoding has checked.
A copied proposal is not an approval, signature, asset attestation or
authorization for a new montage. M57 adds **a separate Pi recovery-intent
contract**, storing only validated metadata and SHA fingerprints without
ever queuing or leasing production work.

New `kidsstudio/recovery_intake.py`:

- Creates an additive `studio_recovery_intents` table in the existing Pi
  Studio Brain SQLite database; no separate job queue.
- Takes an explicitly copied private M56 JSON envelope plus its **exact
  SHA-256 of file bytes**. Rejects symlinks, oversized documents, Git
  checkout paths, malformed envelopes, changed canonical proposal SHA,
  replayed proposal ID, or duplicate recovery for the same original job.
- Opens a single `BEGIN IMMEDIATE` transaction and requires the original
  Pi montage to be FAILED/CANCELLED and its episode reconciled to BLOCKED
  before recording recovery intent. Studio must be unpaused, series ACTIVE.
- Verifies original job request key and exact payload (recipe, parent script,
  frozen M49 catalogue), original request digest, original M32 orchestration
  plan, M51 render contract, M49 scene-set binding and all current ordered
  voice/LTX QA receipts (including their linked audio checks).
- Checks scene count/order, original LTX media digests, valid fallback SHAs,
  bounded recovered-candidate metadata and accurate strategy counts. All
  auto execution/reuse/retry and publication flags must explicitly be false.
- Pins the **new** 32-hex proposal ID independently from the original failed
  job ID. Stores original plan/scene-set/catalogue fingerprints, exact
  transferred envelope SHA, recovery/fallback counts, and state
  `M57_RECONCILIATION_REQUIRED_NO_QUEUE`.
- Audits `M57_PRIVATE_RECOVERY_INTENT_PINNED` on the original Pi job.

## Trust and next activation boundary

The Pi **cannot inspect the original Mac media bytes** from a copied M56
JSON. A successful M57 intake therefore reports
`mac_media_verified_by_pi=false`, `new_pi_job_id=null`,
`auto_execute_allowed=false`, and
`public_release_authorized=false`. A checksum merely pins the exact
file Pi received; it is **not** a cryptographic signature or permission
to use a recovered scene.

No new render is enqueued in M57. A future explicitly authorized
activation must bind a new M14-like catalogue and exact media/scene
receipts to this contract, create a unique fresh Pi queue job, enforce
M52/M53/M54 lease-time and during-render validation, and apply M7 full
final-master QA, educational/rights checks and owner PRIVATE preview.
The original M32 plan and old M49 binding are never overwritten.
A proposal cannot silently become an `episode_assemble` job through
the existing queue or operator CLI.

The user's desired fully AI-internal reviews remain separate from the
owner's final private video acceptance. This milestone adds safety
infrastructure; it does not impose extra human review on every scene.

## Tests

Four synthetic M32 fixture regressions cover successful non-queuing
intake with a new identity, exact duplicate rejection, forged recovered
scene metadata and publish flags, bad envelope/file hash, wrong old job
terminal state, missing episode reconciliation, and changed scene QA.

## Offline command examples (do not run on owner hardware yet)

```sh
python -m kidsstudio.recovery_intake --db /PRIVATE/pi/studio.sqlite --initialize
python -m kidsstudio.recovery_intake \
  --db /PRIVATE/pi/studio.sqlite \
  --proposal /PRIVATE/pi/copied_m56_proposal.json \
  --sha256 EXACT_SHA256_OF_COPIED_JSON_BYTES
```

These commands never run a model, FFmpeg, or publish. Until owner-authorized
device qualification and later activation contracts, keep PR #28 **draft
and unmerged**.
