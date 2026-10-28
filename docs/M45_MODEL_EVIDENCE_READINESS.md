# M45 — One read-only model evidence / pilot readiness report

**Branch:** `feature/m3-series-episode-orchestrator`, draft PR #28.

M45 is not a new generation engine or an artificial "READY" shortcut.
It consolidates M39–M44 actual-byte checks into an owner-readable,
nonauthorizing report without touching Mac/Pi hardware, AI models,
Google OAuth or network services.

## New CLI

`studio-model-readiness --model /PRIVATE/models/qwen-omni-7b
--model-sha256 <actual-M41-package-SHA256>` is read-only by default.

The model directory is always fully re-hashed. Everything else is optional
and clearly marked **NOT_SUPPLIED** rather than guessed.

For an owner-signed existing M44 source attestation add
`--origin-receipt /PRIVATE/.../model_origin_receipt.json`
and `--origin-sha256 <actual-receipt-sha256>`, with the secret owner
key provided in the local `KIDS_STUDIO_MODEL_ORIGIN_KEY` environment.
The HMAC only proves the owner signed *that claim*, never verifies the
upstream weights/revision, independent license rights or content safety.

For a prior M43 local pilot, add its `--adapter`,
`--pilot-metrics`, `--pilot-metrics-sha256`,
`--model-diagnostic`, `--model-diagnostic-sha256`,
and current original `--script`, `--wav` and `--transcript`
(voice) or `--mp4`, `--frames-manifest` and `--ffprobe`
(AV). M45 hashes all original files again and checks exact source
SHA maps, owner origin receipt binding, reviewer executable SHA,
and M42 **UNSURE-only** diagnostic criteria. A mock model, a forged
or outdated media hash, a changed script or an incorrectly promoted
`model_quality_qualified=true` blocks that claimed receipt.

For optional four-case contrast evidence add
`--av-canary-report`, `--av-canary-sha256` and
`--av-canary-manifest`. M45 rehashes the original four real
sound-bearing clip files and demands the M39 report explicitly
disclaim independent ground-truth certification. It does not accept a
case-SHA label table as proof of a trained model's real perception.
Canary SHA matching shows only byte consistency, not whether any
unsafe visuals or audio timing defects were independently confirmed.

The **current** Mac resource prescreen runs again, so a previous M43
report claiming a powerful Mac cannot make a Linux CI host or a
smaller actual Mac pass the real hardware screen.

Run with no `--execute` to inspect/print without any file output.
An explicit `--execute --out /PRIVATE/reports/m45-readiness.json`
only saves a new one-time **NOT PRODUCTION READY** snapshot;
it never launches inference, claims queue work or permits YouTube
PRIVATE/PUBLIC upload. Existing or symlinked output paths are rejected.

## Visible gate groups

| Gate | How evidence is checked | Meaning of a local green |
|---|---|---|
| M41_CHECKPOINT_INTEGRITY | Rehash full checkpoint + member inventory | Same model bytes, not a verified model |
| M44_OWNER_ORIGIN_ATTESTATION | Rehash receipt and copied license; HMAC | Authenticated owner's source claim, not independent provenance |
| M42_CURRENT_MAC_RESOURCE_SCREEN | Re-inspect local resources and 7B identity | Screening only, no MPS inference |
| M43_PINNED_PILOT_OBSERVATION | Rehash original WAV/MP4/script/transcript/frames, adapter and diagnostic | Output integrity with UNSURE decisions only |
| M39_CANARY_CONTRAST_EVIDENCE | Rehash four clips and compare score report | Observed test results with no independently proven semantic truth |

Additional mandatory blockers **always remain**:
independent upstream checkpoint provenance, actual commercial license
adjudication, real Apple MPS inference/RAM stability, Arabic narration
and AV/lip-sync competence, independent ground-truth labels,
authenticated Mac–Pi two-scene delivery, child/educational rights and
safety, separately authorized PRIVATE upload and eventual explicit
owner-only PUBLIC release.

The status is *always*
`M45_EVIDENCE_INVENTORY_NOT_PRODUCTION_READY`, even if all five
local byte/source gates pass. `qualified_gate_count=0`,
`private_upload_permitted=false` and
`public_release_authorized=false` are hard-coded invariants.

## How CI tests this honestly

`tests/test_model_evidence_readiness_m45.py` uses:
real FFmpeg WAV/audio-bearing MP4, private model checkpoint/shards,
mocked M43 subprocess receipt, synthetic copied Apache text with
a test-only owner HMAC, and fake AV canary labels with synthetic
video variants. It also tests changed transcript, altered signed
receipt/owner key, forged green model report, replayed source bytes,
optional canary evidence, read-only default, immutable report save
and explicit negative publish flags.

**No trained model or real Mac resource behavior is validated.**
The report is a trustworthy *catalog of what files were checked*, not
a certification of their contents, legal rights, AI skill or commercial
deployment readiness.

The implementation does not include actual model installation,
Cloud/Google access, publication scheduling or YouTube API calls.
It deliberately leaves those as separate real-device and owner gates.
