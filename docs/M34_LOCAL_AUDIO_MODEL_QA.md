# M34 — local audio-capable independent reviewers → M23/M28 Pi import

**Status:** GitHub branch prototype, not installed or executed on the user's Mac/Pi. CI runs genuine FFmpeg/WAV decoding with intentionally **fake** Whisper and fake audio-review model executables. No real narration understanding, child-safety inference, rights clearance or YouTube upload was tested.

## What M34 changes

Earlier M23 can check the actual WAV format, duration, loudness, clipping and silence. M29 can invoke a configured Whisper.cpp CLI on a WAV and produce a transcript. M28 can import and audit a HMAC-signed private scene review against the *current Pi job*, script, technical evidence, ASR and rights catalogue. **The missing connector was genuine review adapters that receive the WAV itself**, rather than text-only assistants claiming to have listened.

`kidsstudio/local_audio_review.py` provides a conservative, opt-in connector:

1. Require the exact original WAV SHA, exact scene-script TXT SHA, current Pi 32-character job ID, series/episode/scene and a separate rights receipt whose source proof TXT is present. Rights declarations remain claims, **not a legal determination**.
2. Decode and validate the WAV using installed FFmpeg/FFprobe, creating an immutable M23 `voice_technical.json` whose current source identity matches Pi.
3. Actually launch the specifically configured, local Whisper.cpp CLI and pinned `.bin` checkpoint against the source audio, including an isolated 16-kHz PCM copy if necessary; store the actual ASR transcript and SHA evidence.
4. Launch two **separate pinned local executable adapters and two different pinned audio-model checkpoints**. Each executable receives `--wav`, `--script`, `--transcript`, `--model`, `--language`, `--role` and `--output`. One reviewer checks pronunciation, clarity and script fidelity. The independent reviewer checks age appropriateness, emotional tone and audio content safety. Each must actually examine sound, not merely the transcript. Models without audio understanding must return `UNSURE` for unobservable criteria, never assert PASS.
5. Check bounded, strict JSON: `role`, `audio_sha256`, `script_sha256`, `transcript_sha256`, `model_sha256`, `checks`, `summary`. Every criterion must be PASS, UNSURE or NEEDS_FIX with specific evidence. Reject missing criteria, mismatched source/model SHA, missing output, failed model program, timeout, duplicate model checkpoints or executables, or unsafe ownership claims.
6. Sign one exact M28 `signed_voice_m28.json` using the protected, independent `KIDS_STUDIO_SCENE_QA_RUNNER_KEY` worker key, binding the original WAV, source scene, current M23 technical receipt, two model reviews, ASR observations and rights-source catalogue.
7. **Do not approve the scene here.** The Pi must separately `register-scene-voice-qa`, then `register-scene-ai-qa`, then run the existing M28 `auto-approve-scene-stage` command if and only if all independent checks and word-error-rate threshold passed. M33 then advances the corresponding scene within its bounded cycle.

The worker launches FFmpeg, Whisper and both model adapters with an allowlisted subprocess environment; the HMAC signing key, OAuth tokens and unrelated API credentials are not inherited by model subprocesses. CI specifically tests that synthetic parent-process secrets are unavailable inside the mock adapters.\n\nThe private runner's HMAC attests the origin of the *report file*, assuming its secret key remains private. It **does not prove** the reviewed audio was listened to correctly, the checkpoint is competent, the producer owns the rights, or the result is appropriate for children. Actual independently qualified models are necessary before treating the pipeline as autonomous.

## Standalone future invocation, with REAL local approved paths

Install an actual Whisper.cpp model and **two different audio-capable reviewer adapters/checkpoints** outside GitHub; review their provenance and ensure their intended capability is actual WAV perception. Store independent worker secret outside source control. Then:

```sh
studio-real-audio-review \
  --series colors-ar --episode 1 --scene 1 \
  --job-id EXACT_CURRENT_PI_JOB_32_HEX \
  --wav /PRIVATE/scene01_voice.wav \
  --wav-sha256 EXACT_64_HEX \
  --script /PRIVATE/scene01_script.txt \
  --script-sha256 EXACT_64_HEX \
  --language ar --rights /PRIVATE/scene01_rights.json \
  --whisper /PRIVATE/bin/whisper-cli \
  --whisper-model /PRIVATE/models/ggml-model.bin \
  --whisper-model-sha256 EXACT_64_HEX \
  --ffmpeg /PRIVATE/bin/ffmpeg --ffprobe /PRIVATE/bin/ffprobe \
  --first-binary /PRIVATE/bin/child-audio-reviewer-a \
  --first-binary-sha256 EXACT_64_HEX \
  --first-model /PRIVATE/models/child-speech-a.bin \
  --first-model-sha256 EXACT_64_HEX \
  --first-provider child_audio_a --first-model-id child-speech-a \
  --second-binary /PRIVATE/bin/child-audio-reviewer-b \
  --second-binary-sha256 EXACT_64_HEX \
  --second-model /PRIVATE/models/child-speech-b.bin \
  --second-model-sha256 EXACT_64_HEX \
  --second-provider child_audio_b --second-model-id child-speech-b \
  --out /PRIVATE/reviews/scene01_attempt001 --execute
```

Without `--execute`, command is inert and records no model or media activity. Use a unique output directory for every review; existing reports are never silently overwritten. All content stays on the local machine, not GitHub.

## CI: what passes and what remains

`tests/test_local_audio_review_m34.py` builds a **real 16-kHz PCM WAV test tone**, executes actual FFmpeg/FFprobe and an explicitly fake Whisper executable, then executes two different fake local CLI adapters that demonstrably read WAV bytes and generate bounded, SHA-pinned responses. The integration test registers the resulting M23/M28 files against the **current Pi simulated stage and job**, proves M28 can consume them and unlock LTX internally, without inventing owner approval or upload rights. Negative tests reject wrong WAV SHA, rights claims, short secret, duplicate reviewers and output overwrites.

**A real test tone is not speech.** Mock PASS results do not imply phoneme accuracy, emotional tone, safe narration or original intellectual property. This module is an adapter and importer; it does not provide or install any audio model checkpoint and has not executed a real model on user hardware.

M34 is one dependency toward the final pre-hardware cut, not the end of the work. Real audio model selection/qualification, authenticated Mac worker integration, genuine LTX/voice reviews, reliable feedback-based repair recipes, full scene assets/assembly and one authentic complete original episode still need testing. The first integrated Mac/Pi hardware pilot remains blocked until this software qualification is complete. No PUBLIC publishing route is added.
