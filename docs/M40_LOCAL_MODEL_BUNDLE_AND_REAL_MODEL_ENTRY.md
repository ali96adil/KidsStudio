# M40 — Local model runtime bundle (not a model installation)

**State:** Development branch / PR #28 DRAFT. Source code only: no owner Mac/Pi contacted, no model installed or downloaded, no API credentials used, no media uploaded. This work connects **already installed local** audio and audiovisual reviewer executables to the existing M34/M37 signed evidence pipeline, but it does not claim the executables or models are actually available on the owner's Mac.

## What M40 delivers

`studio-model-bundle` consolidates 5 independent roles into one private manifest:
- `asr_whispercpp`: an actual installed whisper.cpp CLI and pinned local ASR checkpoint.
- `audio_pronunciation`: local model CLI to hear the original WAV and judge pronunciation/clarity/script.
- `audio_child_safety`: **distinct executable and checkpoint** to listen and judge child-appropriate audio.
- `av_motion_sync`: AV-capable CLI that must observe the original sound-bearing MP4 and WAV together; never mark lip-sync PASS from silent frames.
- `av_visual_child_safety`: separate AV-capable CLI for visual consistency, age appropriateness and unsafe content.

Each entry contains absolute `binary`, `binary_sha256`, `model`, `model_sha256`, `provider_id`, and `model_id`. Media tools have exact binary SHA fields. All five checkpoints **and the manifest itself** live in an explicit **non-Git, owner-private, non-shared root** (the root must not be group/world-writable). Four review roles must have distinct providers, executables and model checkpoint digests. The ASR provider is exclusively `asr_whispercpp`; it cannot masquerade as the independent reviewer. Files are rehashed at each inspection; missing, symlinked, changed, duplicated or out-of-root checkpoints block execution.

The **manifest itself** must be pinned separately with `--manifest-sha256`; changing any model, tool, provider, or option invalidates the earlier owner-approved bundle digest. All roles are local and opt-in. The manifest **must** declare `network_required=false`, `model_quality_qualified=false`, `execution_authorized=false`, and `public_release_authorized=false`.

There is no online installer, automatic model discovery, plugin download, source artwork generation, actual Pi status change, private upload, or public publishing.

## Private manifest template (illustrative; substitute real absolute paths and digests)

```json
{
  "schema_version": 1,
  "deployment": "local_offline",
  "private_root": "/PRIVATE/KidsStudio/models",
  "network_required": false,
  "model_quality_qualified": false,
  "execution_authorized": false,
  "public_release_authorized": false,
  "tools": {
    "ffmpeg": {"binary": "/PRIVATE/tools/ffmpeg", "sha256": "64_hex_digits"},
    "ffprobe": {"binary": "/PRIVATE/tools/ffprobe", "sha256": "64_hex_digits"}
  },
  "reviewers": {
    "asr_whispercpp": {
      "binary": "/PRIVATE/bin/whisper-cli", "binary_sha256": "64_hex_digits",
      "model": "/PRIVATE/KidsStudio/models/whisper.bin",
      "model_sha256": "64_hex_digits", "provider_id": "asr_whispercpp",
      "model_id": "whisper-local"
    },
    "audio_pronunciation": {
      "binary": "/PRIVATE/bin/audio-review-a", "binary_sha256": "64_hex_digits",
      "model": "/PRIVATE/KidsStudio/models/audio_a.gguf",
      "model_sha256": "64_hex_digits", "provider_id": "local_audio_a",
      "model_id": "audio-a-local"
    },
    "audio_child_safety": {
      "binary": "/PRIVATE/bin/audio-review-b", "binary_sha256": "64_hex_digits",
      "model": "/PRIVATE/KidsStudio/models/audio_b.gguf",
      "model_sha256": "64_hex_digits", "provider_id": "local_audio_b",
      "model_id": "audio-b-local"
    },
    "av_motion_sync": {
      "binary": "/PRIVATE/bin/av-review-a", "binary_sha256": "64_hex_digits",
      "model": "/PRIVATE/KidsStudio/models/av_a.safetensors",
      "model_sha256": "64_hex_digits", "provider_id": "local_av_a",
      "model_id": "av-a-local"
    },
    "av_visual_child_safety": {
      "binary": "/PRIVATE/bin/av-review-b", "binary_sha256": "64_hex_digits",
      "model": "/PRIVATE/KidsStudio/models/av_b.safetensors",
      "model_sha256": "64_hex_digits", "provider_id": "local_av_b",
      "model_id": "av-b-local"
    }
  }
}
```

All `64_hex_digits` placeholders must be replaced with the **actual SHA256**; this example is **not runnable**. The current M34/M37 interface supports one explicitly pinned `.bin`, `.gguf` or `.safetensors` checkpoint per model. Multi-file Hugging Face models need a separately designed and audited directory manifest / adapter before they can work here. **Never invent a one-file SHA to represent an entire model repository.**

## Commands (only for future explicitly approved local pilot)

```sh
# Owner first calculates the actual private manifest digest:
shasum -a 256 /PRIVATE/KidsStudio/models/model_bundle.json

# Pure local inspection: no model invocation or Pi write
studio-model-bundle \
 --manifest /PRIVATE/KidsStudio/models/model_bundle.json \
 --manifest-sha256 <actual-64-char-digest> inspect

# Scene-specific voice/MP4 commands also default to inspection only.
# Only a separate --execute, current job ID, media checksums, M10/rights
# and a private HMAC worker signer will invoke M34 or M37.
studio-model-bundle --help
```

The result contains no private paths, only role IDs and checksums, and reports `M40_LOCAL_MODEL_BYTES_PINNED_NOT_QUALIFIED`. Even a successful runtime call reports `real_model_competence_proven_by_m40=false`, `pi_scene_approved=false`, `private_upload_permitted=false`, `public_release_authorized=false`. Current-source Pi acceptance still requires independent M35/M37 imports; model runtime itself cannot accept a scene.

The runner processes do not inherit the scene HMAC or OAuth secrets via `media_subprocess_env`. **This is not a full OS network sandbox**: a malicious binary can still make its own outbound requests or read files accessible to the process. Real installation requires a restricted machine/user and verified offline execution behavior. No external service should be configured without authorization.

## Real-model candidate and feasibility warning

A documented *research candidate* is Qwen2.5-Omni Thinker, which supports combined video + audio decoding and aligned multimodal inputs (Hugging Face Transformers and QwenLM documentation). It is not implemented as an M40 adapter, installed, or measured on the owner Mac. The QwenLM repository lists a **theoretical minimum ~18.38 GB GPU memory for its 3B BF16 version processing a 15-second video** and notes real use is typically at least 1.2× higher. This makes it inappropriate to assume that the owner's memory capacity or available disk can run it. A single general-purpose Omni model is also **not proof of frame-accurate lip-sync or suitability for children**; such criteria still need independently ground-truthed M39 canary evaluation, potentially a dedicated viseme synchrony model.

A practical pilot therefore starts with **inspection of installed models and device resources**, then calibration against **genuine independently labeled** clean/offset/wrong-narration/unsafe-content clips, and only after that runs one PRIVATE-only two-scene proof on the owner hardware. Until then, all model-quality, rights and publishing gates are blocked.

## CI scope

`tests/test_model_runtime_bundle_m40.py` uses real binary file hashes and FFmpeg media, but **fake Whisper, fake audio reviewers, and fake AV reviewers** from M34/M37 fixtures. It checks exact manifest SHA, missing or altered checkpoint, shared provider/binary/checkpoint, out-of-root and symlink checkpoint, forbidden policy flags, no-execute behavior, and actual M34/M37 bridging with the mocked reviewers. CI **does not test training, model inference, lip-sync competence, or Mac GPU performance**.

## Next actionable dependencies

1. On real owner Mac, collect RAM, macOS, actual private toolchain and model inventory *read-only* through M39 and this manifest; do not install or download new models automatically.
2. Select real local audio-capable and time-aligned audiovisual checkpoints that fit the Mac, including licenses and commercial-use compatibility; build **audited** adapters for each, verify actual network isolation and run genuine M39 canaries.
3. Independently verify exact Pi M21 TLS freshness and one real worker lease/ACK/return, then run one original two-scene local pilot **without YouTube upload**.
4. Separately authorize a single YouTube **PRIVATE** video upload for the owner's accept / accept-with-notes / request-changes review; no automatic PUBLIC transition.
