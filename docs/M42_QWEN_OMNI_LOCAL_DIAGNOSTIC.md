# M42 — Local Qwen2.5-Omni Thinker diagnostic adapter, safe by default

**Development branch / PR #28 DRAFT only.** The code has NOT been run
on the owner's Mac or Raspberry Pi. No trained model, external package,
model weights or paid API has been installed. No media was uploaded.

## Purpose

M42 adds `kidsstudio/qwen_omni_local.py` /
`studio-qwen-omni-adapter`. It is the first concrete implementation
candidate of the existing M34/M37 CLI contract for a publicly documented,
real multimodal model runtime: **Qwen2.5-Omni Thinker** through
Hugging Face Transformers. Qwen's official examples use
`Qwen2_5OmniThinkerForConditionalGeneration` with
`Qwen2_5OmniProcessor.apply_chat_template` to understand audio,
video with its soundtrack, and text together, without synthesizing audio.

Source documentation:
- https://github.com/QwenLM/Qwen2.5-Omni
- https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/qwen2_5_omni.md

**Important:** This is a *candidate implementation*, not a verified
on-device model or a qualified children's reviewer. It can fail on
Apple MPS due to memory, unsupported operations, or different installed
Transformers versions. Its real inference branch cannot be proved in
ordinary GitHub Linux CI; those tests use fake inference only.

## What the adapter really does

1. **Read-only inspection:** SHA256 re-verifies the entire pinned M41
   `model_files.json` directory, checks local Qwen config type,
   confirms Apple Silicon macOS, verifies physical RAM, free storage
   and installed local `torch`, `transformers` and `torchvision`.
   It does **NOT** import the model or test MPS. A green *resource
   screen* is NOT a hardware test, inference, model competence or
   permission to publish.
2. **Real audio path (opt-in):** accepts M34 arguments `--wav`,
   `--script`, `--transcript`, `--model`, `--language`,
   `--role` (`pronunciation` or `child_audio_safety`) and
   `--output`. Loads the exact private WAV into a multimodal
   processor together with the script and ASR evidence. WAV must
   contain bounded 16-bit PCM and be no longer than 20 seconds.
3. **Synchronized AV path (opt-in):** accepts M37 arguments
   `--mp4`, `--wav`, `--script`, `--frames-manifest`,
   `--model`, `--role` (`motion_sync` or
   `visual_child_safety`) and `--output`. FFprobe verifies that
   an MP4 has **both real video and audio** and is no longer than
   10 seconds. The request includes the original sound-bearing MP4,
   the separately hashed WAV, scene text and frame evidence.
   The Transformers processor uses `use_audio_in_video=True`,
   `load_audio_from_video=True` and a bounded 1-fps sample rate.
   Sampling at 1 fps does not establish frame-accurate lip-sync.
4. **Fail-closed results:** Even if the model literally answers
   `PASS` for every criterion, the adapter **returns UNSURE for
   all M34/M37 criteria**. This preserves exact source/checkpoint
   SHA and reporting schemas, but prevents an uncalibrated general
   model from advancing the Pi AI approval gate. A future independent
   calibrated reviewer may detect hard failures, but Qwen's claim
   alone is not evidence for commercial rights or child suitability.
5. **No download or remote model code:** only an existing, SHA-pinned
   local model directory; `local_files_only=True`,
   `trust_remote_code=False`, offline Hugging Face settings and
   explicit Apple MPS device. There is no implicit CPU fallback.
   The adapter creates a new private JSON once; overwrite is refused.
   Sources, transcript, frames and checkpoints are rehashed after
   inference. It never signs a Pi M28 report itself, never connects
   to Pi, and never accesses YouTube.

This is **not a complete OS network sandbox**: an already installed
Python dependency is executable code. A genuine hardware pilot requires
a restricted user/process and an independently verified offline
environment. The allowed source data itself is untrusted; the Qwen
prompt explicitly does not follow instructions in scripts/media.

## Conservative resource prescreen — not an official hardware guarantee

For a first 10-second Apple Silicon trial, the M42 *screening floors*
are:

| Candidate | Physical unified RAM (floor) | Free storage (floor) |
|---|---:|---:|
| Qwen2.5-Omni 3B | 32 GiB | 20 GiB — **commercial pilot BLOCKED: research-only model license** |
| Qwen2.5-Omni 7B | 64 GiB | 40 GiB |

These are **our conservative local trial thresholds**, NOT Qwen's
published minimums for Apple MPS. Qwen's repository quotes a
theoretical **18.38 GB GPU memory minimum** for 3B BF16 with a
15-second video on their Transformers/FlashAttention 2 setup, usually
at least **1.2x more in practice**; the comparable 7B figure is
31.11 GB theoretical. Mac MPS behavior must be observed separately.
Model sizes, unlisted runtimes and storage can require more.
The selection `--variant 3b/7b` is not accepted merely as a user
label: M43 checks the pinned Qwen thinker text configuration against
the upstream 3B/7B architectural identifiers (3B: 2048 hidden,
36 layers; 7B: 3584 hidden, 28 layers). This is only a **config
signature**, not an authenticated upstream source or model license.
Qwen2.5-Omni **3B** is distributed under the Qwen Research License
which restricts commercial use; Kids Studio's commercial pilot
blocks it by default even if the Mac has enough RAM. Qwen2.5-Omni
**7B** is listed under Apache-2.0; exact installed checkpoint
provenance, third-party dependencies and applicable license obligations
still require an independent owner review before commercial deployment.
Official model licenses:
https://huggingface.co/Qwen/Qwen2.5-Omni-3B/blob/main/LICENSE
and https://huggingface.co/Qwen/Qwen2.5-Omni-7B/blob/main/LICENSE. Never treat the screen as
proof the checkpoint is the stated model size.

## Future command examples — DO NOT run until separately authorized

The pinned private model directory is created by M41, and requires
`config.json` with `model_type=qwen2_5_omni` and exact full
package SHA.

```sh
# No inference, downloads or model import:
studio-qwen-omni-adapter \
  --model /PRIVATE/models/qwen2_5_omni_7b \
  --model-sha256 <actual-64-hex-digest> \
  --variant 7b --inspect

# The CLI review mode is also dry-run by default.
# Only a separately authorized real pilot can supply --execute,
# exact original media and a NEW private --output path.
studio-qwen-omni-adapter --help
```

The M34 and M37 worker launchers already constitute explicit
execution points: if this candidate is selected as one role's pinned
executable, a role-specific owner-reviewed wrapper must pass a
literal `--execute` to this CLI. The wrapper itself must be independently
SHA-pinned in M40, and an entire M40 `studio-model-bundle`
`voice/video --execute` call remains required to run it.
**Do not duplicate wrappers to make one model look like two independent
AI reviewers.** The other role requires a genuinely separate
model/implementation/provider and a separate successfully validated
ground-truth dataset.

M42's `UNSURE` gate is intentionally **not the finish line**:
the next milestone must qualify a capable, independent real reviewer
and provide actual measured Mac GPU and end-to-end AV results before
any model may mark a scene PASS. Even then, final video goes to YouTube
**PRIVATE** for owner review, and PUBLIC is a separate explicit decision.

## CI evidence

`tests/test_qwen_omni_local_m42.py` runs real FFmpeg WAV+sound-bearing
MP4, SHA-pinned synthetic multi-file checkpoint, read-only resource
screens, all four adapter role contracts, and deliberately false
model text claiming `PASS`. It proves that false PASS is downgraded
to `UNSURE` and that source, transcript, frame and checkpoint mutation
prevents output. CI also confirms no model is imported on Linux and
direct CLI defaults to no inference. **All semantic inference in CI
is fake**: no trained Arabic/AV model, no 3B/7B GPU run and no
independent child-safety evidence.

The project is still Draft; no device installation or upload occurred.
