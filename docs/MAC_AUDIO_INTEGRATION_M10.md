# M10 — Owner-Mac intake and WAV-to-LTX audio continuity

STATUS: Source code and synthetic tests on draft PR #28 ONLY. Nothing is
installed or running on owner Mac/Pi; no real Chatterbox/LTX inference,
API costs, cloud transfer, auto upload or public YouTube publication.

## Read-only owner Mac contract

A new one-shot CLI, studio-mac-contract, validates a private JSON file with
schema_version=1, private_roots (1 to 4 owner-approved roots), assets,
tools, engine_manifests and minimum_free_gib. All asset scripts and media
must have exact SHA256, explicit absolute non-symlink paths under the roots.
Runtime tools are pinned by executable SHA256 and may live outside the roots.
It requires the approved script, original Bunny reference, voice and LTX
wrapper source, v06/v07 face adapters, two Python interpreters, FFmpeg,
FFprobe, and the two checkpoint manifests. The M8 engine qualifier verifies
Mac/Darwin/Apple-Silicon context, RAM and pinned model checkpoint bytes.

Use distinct private roots for the main project and ComfyUI-Shared if needed.
Original artwork, model weights, WAV/MP4, passwords and paths are not returned
to GitHub. A passing result says
PINNED_LOCAL_MAC_ASSETS_VERIFIED_ENGINES_NOT_RUN, not WORKING ENGINE.

Future one-shot command after user approves installation:

    studio-mac-contract --manifest /PRIVATE/KidsStudio/mac_contract.json

This does NOT run either model, prove the wrapper API works, or verify
commercial licenses. Actual wrapper commands are STILL unqualified and must
be checked against the owner's installed local engines.

## Audio comparison with LTX video soundtrack

The new studio-audio-continuity tool uses OFFLINE FFmpeg to decode WAV and
the selected audio stream embedded in MP4 to 8 kHz mono PCM for up to 180s.
It checks exact SHA256 of both source files before and after read, 20-ms RMS
loudness envelopes, estimated lag within 600ms, silent/missing audio and
grossly unequal durations. An envelope correlation >= 0.82 and duration
difference <= 1.2s means only that an audio energy-profile is compatible.
This heuristic has NOT been calibrated as a voice identity classifier.

A passing report is AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED.
A failing report is AUDIO_CONTINUITY_UNVERIFIED.
Neither status proves the actual spoken words, reference voice identity,
pronunciation, rights or Bunny lip-sync; all need HUMAN evaluation.

Future one-time private Mac action:

    studio-audio-continuity \
      --voice /PRIVATE/scene.wav --voice-sha256 EXACT_SHA \
      --a2v /PRIVATE/scene.mp4 --a2v-sha256 EXACT_SHA \
      --ffmpeg /PRIVATE/ffmpeg --report /PRIVATE/audio_check.json

The report is saved only to an owner-specified PRIVATE non-overwriting file.

## Optional provenance gate in Studio Brain (M10)

Later, after owner-approved deployment, initialize the additive table:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite init-audio-evidence

Then import the trusted report in the same private operator environment:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
      register-audio-evidence colors-ar 1 --report /PRIVATE/audio_check.json

M10 compares that report to the exact approved M6 voice WAV receipt and
CURRENT LTX video receipt. With M10 schema active, LTX approval is blocked
until this technical evidence is registered. The owner must STILL watch and
approve the actual video separately. The Arabic read-only dashboard shows
continuity separately, not as a fake "lip-sync passed" badge.

The report must be transferred explicitly and safely from Mac to Pi if the
Studio Brain SQLite host differs. No transfer service is implemented here.

## Remaining acceptance blockers

1. Pin and qualify actual installed Chatterbox MLX and LTX 2.3 MLX APIs on
   the owner Mac, including voice B settings and exact wrapper scripts.
2. Real full-episode WAV->A2V generation, safe resource use and artist review.
3. M7 technical/educational/rights QA and proven independent recovery backup.
4. Separate owner-initiated manual private preview after archive verification.
5. Migration assessment for standalone Control Center v1-v3 if it contains
   data not already recorded in canonical Studio Brain.
6. Keep pull request in DRAFT; do not merge, deploy or publish without
   the later single owner-authorized end-to-end device acceptance.

All CI tests use synthetic media, fake local asset files and injected platform
information. Passing CI does NOT prove a real audio model ran successfully.
