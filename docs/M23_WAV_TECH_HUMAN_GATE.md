> **M28 update (opt-in):** The original owner-listening requirement remains for the legacy M23 approval command, but the new [AI scene QA gate](M28_AI_SCENE_WAV_LTX_QA.md) can internally approve the same pilot after real technical WAV verification, signed independent AI evidence, transcript comparison and rights-source evidence. The owner should review the full video after PRIVATE upload, not each WAV. Actual ASR/vision model execution on user hardware remains unqualified.\n\n# M23 — Real WAV technical QA + separate owner listening gate

**Implementation:** Draft PR #28 on GitHub only. No real owner Mac/Pi
installation, no Chatterbox or LTX model invocation, no original/personal
audio imported, no paid services and no video publication. CI uses
original, synthetic 440 Hz test tones, clipped waves and silent WAVs.

## What changed

M22 can receive a voice job receipt (SHA256 and byte count) and the
pre-existing M13 scene ledger can mark it `PENDING_QA`. Before M23,
the owner could approve even the M22 pilot WAV without any technical
decode/audio-quality evidence. Now, **for the special scene-1 M22
`pilot_scene=1` jobs only**, the workflow is:

1. The Pi first receives a normal, valid `VOICE_RENDERED_PENDING_QA`
   job receipt containing exact WAV SHA256, byte count and job ID
   (the actual WAV is still stored privately on the Mac).
2. Owner runs local `studio-voice-qa` on that **exact job WAV**.
   FFprobe checks the WAV/PCM codec, mono or stereo, 16–96 kHz,
   a single audio stream, 0.2–180 s and the exact SHA256;
   FFmpeg then decodes the **whole** audio into bounded 16 kHz mono
   signed samples. Numeric heuristics flag silent, very low-level,
   extremely clipped or mostly quiet output. This does NOT check
   speech correctness, pronunciation or musical merit.
3. Technical PASS produces a new immutable private JSON report:
   `VOICE_TECH_PASS_OWNER_LISTENING_PENDING`; it explicitly says
   `owner_listening_performed: false`, voice/text correctness and
   speaker identity unverified, rights unverified and no publication.
   A failed report never unlocks the owner review.
4. Owner registers the report in the Pi M13 ledger with
   `register-scene-voice-qa`; it verifies the same job ID, current
   `PENDING_QA` stage, completed Pi media receipt, WAV SHA, bytes,
   original scene-script SHA and every technical check. The report
   digest is stored in the new `studio_scene_voice_checks` table.
   Duplicate registration is refused. Pi stores no actual audio.
5. The **owner listens independently** on the Mac, comparing the
   narration to the approved words and considering child suitability,
   pacing, pronunciation, speaker/voice rights, and sound quality.
   Only after that explicit real review can the owner invoke the
   existing `approve-scene-stage` command with the *new*
   `--owner-listened` flag, exact WAV SHA and meaningful note. Both
   the pinned M23 report and explicit listening attestation are
   required for M22 pilot voice approval. No auto-approval occurs.
6. Once the scene-1 WAV is actually owner approved, M13 allows a
   separately queued owner-pinned LTX job. LTX still has its own
   real audio/video identity and owner-review checks, and its
   original Bunny reference and checkpoint license must be verified.

## Future command examples (NOT executed on owner devices)

Create private report *after* a real owner-authorized voice job exists:

```sh
studio-voice-qa \
  --wav /PRIVATE/KidsStudio/output/EXACT_JOB_ID/narration.wav \
  --sha256 EXACT_OWNER_PINNED_WAV_SHA256 \
  --job-id EXACT_JOB_ID \
  --script-sha256 EXACT_SCENE_1_SCRIPT_SHA256 \
  --report /PRIVATE/KidsStudio/reviews/scene01_voice_qa_v1.json
```

Import the SHA-bound report at the **Pi coordinator device** via
owner-only Studio Brain CLI:

```sh
python -m kidsstudio.series_cli --db /PRIVATE/pi-brain.sqlite \
  register-scene-voice-qa colors-ar 1 1 \
  --report /PRIVATE/KidsStudio/reviews/scene01_voice_qa_v1.json
```

Do **not** use `--owner-listened` until a human has genuinely listened:

```sh
python -m kidsstudio.series_cli --db /PRIVATE/pi-brain.sqlite \
  approve-scene-stage colors-ar 1 1 \
  --stage voice_synthesize \
  --sha256 EXACT_OWNER_PINNED_WAV_SHA256 \
  --owner-listened \
  --note "I listened to the exact narration and verified words, clarity and rights."
```

Private path placeholders shown above are examples only. The Mac and
Pi report must be transferred manually by an owner-approved secure path;
this feature does not implement automatic transfers. Reports can contain
media hashes and sensitive production metadata and should remain
outside version control.

## What CI proves — and what it does not

Real FFmpeg/FFprobe tests generate small local PCM WAVs and verify full
sample decode, exact media SHA, finite duration, audibility, clipping,
silent input rejection, corrupted input rejection and no decode of
wrong-SHA audio. SQLite tests use the actual StudioQueue/SeriesManager/
SceneLedger and check that missing, duplicate, forged, failed or
wrong-job reports cannot approve M22 voice or start LTX. A separate
explicit synthetic owner event allows the gated transition to
`QA_APPROVED` and demonstrates the normal downstream LTX queue path.

These numerical audio checks are intentionally imperfect: a noise
wave or test tone can pass while being unsuitable for children.
`--owner-listened` records an attestation, **not proof** that a human
has in fact listened. Commercial rights, character consistency,
educational/script correctness, safe narration and publication require
independent substantive owner inspection and documentation.

Legacy M13 scene-stage approvals are unchanged: the mandatory M23
report and `--owner-listened` apply only to `pilot_scene=1` jobs
created through M22; they do not retroactively invalidate older
approved projects.

**Remaining:** real Chatterbox model/wrapper qualification on Mac,
actual original narration, owner review, LTX animation, final M7
quality/rights, reliable backups and separate owner-authorized
PRIVATE YouTube upload. Nothing is deployed or published in M23.
