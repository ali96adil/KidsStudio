# KidsStudio — M29 Local Media Evidence and Vision Bridge

**Current status: development branch only, not a Mac/Pi installation.**
These commands only run when explicitly executed locally. No uploads,
YouTube visibility changes, autonomous publication, remote AI,
model downloads, or new hardware configuration.

## Real sources rather than fabricated reports

`studio-capture-real-evidence frames` runs the pinned, installed
FFprobe and FFmpeg binaries against the exact SHA-256 source MP4,
checks the first video stream and duration, samples 3–12 timestamps
across the actual video, saves bounded PNG outputs, hashes each
frame and a manifest, and rehashes the original MP4 afterwards.
Missing media, wrong SHA, malformed video, bad output, unavailable
binaries or already-existing output paths fail closed.

`studio-capture-real-evidence asr` runs an explicitly provided
**local whisper.cpp `whisper-cli` executable** against a local WAV,
an exact owner-pinned script TXT and owner-pinned local Whisper
`.bin` model. It records actual CLI execution, source hashes, model
hash and UTF-8 transcript bytes. Whisper's 16-kHz mono PCM16 input
is verified; an original 48-kHz WAV can be converted to a separate
private inference copy using explicit FFmpeg, without changing the
pinned original recording. The input hash and conversion flag are
recorded. There is no generated AI reviewer PASS and no claim that the
words, pronunciation, language choice or copyright are correct. The first test pass uses a synthetic fake
Whisper CLI executable; user-model quality is NOT yet verified.

Example safe invocation (future Mac only, with **real** paths and SHA):

```sh
studio-capture-real-evidence asr \
  --wav /PRIVATE/scene_voice.wav \
  --wav-sha256 EXACT_WAV_SHA \
  --script /PRIVATE/scene_script.txt \
  --script-sha256 EXACT_SCRIPT_SHA \
  --whisper /PRIVATE/bin/whisper-cli \
  --model /PRIVATE/models/ggml-medium.bin \
  --model-sha256 EXACT_MODEL_SHA \
  --ffmpeg /PRIVATE/bin/ffmpeg \
  --language ar --out /PRIVATE/runs/scene01_asr_v01
```

This is opt-in to keep private original assets on the machine.

## Actual independent vision model calls

`studio-real-vision-review` reads the exact source MP4/script
hashes, a separate owner-curated source-rights catalogue and
**two different, explicitly configured loopback-only Ollama
processes (distinct local port and model)**. It invokes M29 actual
FFmpeg frame capture and sends the captured PNGs to each
`http://127.0.0.1:PORT/api/chat` using vision-model image input.
It requests role-specific JSON checks and refuses missing or
malformed evidence. Every reviewer must choose PASS/UNSURE/NEEDS_FIX.
The prompt explicitly instructs the models to return **UNSURE**
for audio lip-sync and voice properties they cannot hear from
silent frames. These cannot legitimately be certified solely from
the PNG images.

After actual local model calls, the worker writes an **unapproved**
`model_report_pending_m10.json` and `observations.json`.
`studio-bind-vision-m10 --execute` validates exact M10
audio-continuity report bytes and SHA, same MP4/source WAV
lineage and independent reviewer IDs, then signs the full M28
bundle using the local private
`KIDS_STUDIO_SCENE_QA_RUNNER_KEY`.

The signed bundle is STILL **not** approval: Pi M28
`register-scene-ai-qa` must match current Pi stage, technical
M10 receipt SHA, script/job/MP4 hashes, source/rights proof and
real frame files, and all reviewer criteria must PASS before
`auto-approve-scene-stage` is allowed. The owner watches the
complete video only after later YouTube PRIVATE upload.

This separation intentionally prevents an M29 vision-model reply
from masquerading as an approved video or from publishing anything.

## What GitHub CI actually proves

M29 CI runs a **real FFmpeg decode** of a synthetic H.264 MP4
and verifies exact frame hashes and failure on wrong media SHA.
It tests the Whisper CLI protocol using a **synthetic fake binary**
(not a real ASR inference). Two **fake Ollama HTTP responders**
check that two differently configured local models would receive
the real extracted image bytes. It tests response schema, M10
binding, signer and missing evidence behavior.

These tests **do not** prove real character quality, voice
pronunciation, intended educational value, rights ownership, LTX
lip-sync, a local Whisper model install, Ollama vision checkpoints,
or successful Pi→Mac remote operation.

## Release-candidate cut: when to stop coding and test hardware

No full user-hardware production test while a required software
capability is missing. Before issuing a single integrated smoke test
pack, all of these software contracts must be implemented and
pass synthetic integration CI:

1. Actual Arabic/English ASR recording and **audio-capable
   independent QA review** across every scene (not just M22 pilot).
2. Actual multimodal scene reviewers integrated with current Pi
   technical evidence, with automatic feedback and bounded
   regeneration when criteria need correction.
3. Actual independent AI script/educational/rights evaluation,
   removing repeat owner script signoffs without creating a
   fake approval event.
4. A real completed original two-scene production pipeline from
   script through art/rig/voice/animation/assembly, with reproducible
   inputs, artifact provenance and no manual per-scene clicks.
5. One-button/invocation Studio Brain orchestration and truthful
   dashboard showing each stage, blocked reason and next action.
6. M24 final owner review retained AFTER YouTube PRIVATE; no
   PUBLIC API without separate owner action.

After those software checkpoints are implemented and CI green,
the **first actual device test** is one integrated pilot on the
Mac/Pi (local only, with YouTube connectivity OFF), then real
PRIVATE upload OAuth qualification as a separately owner-approved
stage. It is not productive to test OAuth before producing a
qualifying original master video.

**This document is the freeze target, not a claim that these six
conditions have been met.** No percentage of completion should be
claimed without real qualification.
