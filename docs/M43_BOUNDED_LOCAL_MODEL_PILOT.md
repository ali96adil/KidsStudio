# M43 — Bounded one-shot Mac model pilot (PRIVATE, offline, not an AI approval)

This milestone implements **`studio-model-pilot`**, a single-scene,
single-role local diagnostic runner for an already installed M42
Qwen2.5-Omni Thinker executable. No real Mac/Pi was contacted during
development. No model was downloaded, trained or imported on GitHub.
The feature is opt-in and remains in draft PR #28.

## What M43 specifically closes

M42's JSON adapter could run directly, but its prior CI could only prove
interface shape with a **mock response**. M43 now gives the owner a
repeatable, bounded procedure for an *actual model* later, without
implicitly certifying that it understands spoken Arabic, can lip-sync,
checks age-appropriate visuals, or has rights to distribute a video.

The probe:

- Rehashes the exact M41 sharded checkpoint package and installed
  SHA-pinned local M42 adapter before executing anything.
- Rehashes the original scene WAV and TXT. Voice roles additionally
  require an exact ASR transcript TXT. AV roles require a sound-bearing
  original MP4, the actual bounded M37 frame manifest, and an explicitly
  SHA-pinned FFprobe binary.
- Calls the **current M42 Apple Silicon resource screen** for owner Mac
  memory, disk and locally installed dependencies. An insufficient Mac
  blocks execution before an output folder is created.
- Defaults to **read-only** even if all inputs are valid. It needs a
  deliberate `--execute` to create a new private output directory and
  start a pinned local subprocess, **once**, without retry.
- Has an explicit deadline up to 900 seconds. It does not inherit
  OAuth or HMAC keys, and sets the HF/Transformers offline environment.
  Its deadline is an upper limit, not an expected runtime.
- Independent of the model's prose claims, checks the M42 diagnostic
  JSON: each role-specific verdict must be `UNSURE`. Any `PASS`,
  `NEEDS_FIX`, missing role, mismatched bytes, malformed response,
  changed source or partial failed execution prevents a metrics receipt.
- Records bounded wall time and an observational child-process maximum
  resident set size (RSS), **not** exact Apple unified/GPU memory.
  `resource.getrusage(RUSAGE_CHILDREN)` may include earlier children in
  a long-lived caller; use a fresh CLI process per run. A successful
  mock or real run still returns `model_inference_proven=false` and
  `model_quality_qualified=false` because the process alone cannot
  prove semantic capability, independent safety or acceptable accuracy.
- Never imports a scene into Pi SQLite, never signs M28 approval,
  never claims rights clearance and **never uploads or publishes**.

The resulting directory has `m42_diagnostic.json` (unqualified model
observation) and `pilot_metrics.json` (pinned sources, wall time and RSS
watermark). Neither contains raw media, secret keys or captured stdout/
stderr. They are created under an explicitly owner-private directory
outside Git. Failed or timed-out executions are **not** usable as quality
evidence; a fresh run requires a new directory name.

## Illustrative command — only after later real owner-Mac authorization

```sh
# Dry run, local and read-only:
studio-model-pilot \
  --adapter /PRIVATE/bin/studio-qwen-omni-adapter \
  --adapter-sha256 <actual-binary-digest> \
  --model /PRIVATE/models/qwen2_5_omni_3b \
  --model-sha256 <actual-complete-package-digest> \
  --variant 3b --role pronunciation \
  --wav /PRIVATE/scene01.wav --wav-sha256 <actual-WAV-digest> \
  --script /PRIVATE/scene01.txt --script-sha256 <actual-script-digest> \
  --transcript /PRIVATE/asr-scene01.txt \
  --transcript-sha256 <actual-ASR-TXT-digest> \
  --out /PRIVATE/diagnostics/m43-scene01-voice
```

The same command with a separately authorized `--execute` starts a
single genuine local model call only if the Mac screening gate passes.
For AV roles `motion_sync` or `visual_child_safety`, replace the
`--transcript` pair with `--mp4`, `--mp4-sha256`,
`--frames-manifest`, `--frames-sha256`, `--ffprobe` and
`--ffprobe-sha256` pairs. All actual values must be owner-provided
pinned bytes; placeholders are non-runnable.

There is **no automatic model installer**. The executable must already
exist and be properly wrapped, especially if the package's entrypoint
is a Python module with a script. An adapter-only success is not a pass
in M39's independently labeled clean/offset/wrong-voice/unsafe-video
canary benchmark; those canaries remain necessary. The M42 adapter
intentionally cannot emit PASS yet.

Official upstream reference for the optional Qwen candidate:
https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/qwen2_5_omni.md

## CI evidence and limitations

`tests/test_model_pilot_probe_m43.py` uses actual FFmpeg WAV and
audio-bearing MP4 sources plus a test-only, SHA-pinned executable that
does NOT run any model. It verifies zero calls on read-only preflight,
bounded one-shot execution, source/runner/model/ffprobe binding,
audio/video report shape and exact UNSURE decisions, replay avoidance,
blocked resource screens, wrong SHA checks, timeout and rejection of a
fabricated PASS response.

**The CI resource screen is synthetic**, as if run on a sufficiently
provisioned Apple Silicon machine; no Mac, real Qwen model, MPS GPU
allocation, Transformers inference or educational review is tested.

Until genuine Mac hardware measurements, offline isolation checks,
qualified real independent reviewers, legitimate model/content rights
and owner video inspection, no YouTube PRIVATE upload may be authorized.
PUBLIC remains a distinct explicit owner-only decision, even after the
future private review.
