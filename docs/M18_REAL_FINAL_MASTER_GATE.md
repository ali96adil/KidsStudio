# M18 — Real Final-Master QA and Scene-Audio Continuity (GitHub CI)

**Scope:** Code-only validation in **draft PR #28**. No Mac/Pi deployment,
actual Apple Silicon Chatterbox/LTX calls, real Bunny art, private narration,
paid API, channel access, or media upload.

## Gap closed

M17 used real Linux FFmpeg/FFprobe to make two generated color-and-tone clips,
normalize and combine them into an MP4. M7 final quality checks had been
exercised against synthetic bytes with **stubbed** ffprobe/decode functions,
rather than the assembled MP4.

M18's `tests/test_real_ffmpeg_m18.py` exercises the real M4 → M7 chain:

1. Generate two **original test-only** 384x384, 24fps, 1.5s H.264/AAC
   clips, red with 440Hz tone and blue with 880Hz tone. These are not a
   children's episode and use no AI/voice model.
2. SHA-pin the actual input clips and script, run the real EpisodeAssembler,
   verify sources remained immutable, and obtain the new master's SHA.
3. Pass the actual master and exact SHA to **real** `inspect_video` with
   system `ffprobe` and `ffmpeg`; require all M7 codec, track, resolution,
   fps, 48kHz, 2–900s duration and **full audio/video decode** checks.
4. Decode two separated PCM windows of the **master**, not source clips.
   Detect real rising zero-crossings near 440Hz in scene 1 and 880Hz in
   scene 2, proving that each distinct synthetic audio scene was retained
   in approximate time order. This is **not** proof of real human lip sync.
5. Feed a **wrong queue-receipt SHA** to M7: it must fail and refuse to
   decode the untrusted video. Change a source scene after pinning: M4
   preflight must refuse before creating a render directory.
6. Confirm machine `TECH_PASS_OWNER_REVIEW_PENDING` leaves subjective
   review, rights and publishing approval **false**.

GitHub CI explicitly installs FFmpeg/FFprobe in both Python jobs; the
integration test **fails** if either binary is missing. No test silently
skips actual subprocess media execution.

## Defect discovered and corrected

The first M18 real integration run failed safely: although both normalized
clips were 24fps, MP4 concat `-c copy` shifted boundary packet timestamps
around AAC priming. The resulting final master exposed a non-24
`r_frame_rate`, so M7 correctly returned `TECH_FAILED` before full decode.
On disposable local synthetic files, explicit final 24fps H.264/AAC
encoding yielded exact `24/1` output and successful full decode.
M4 now final-encodes the concatenated QA master with `fps=24` instead of
trusting container stream copy. M18 is the regression test; final CI must
pass before claiming the gate is green. It may add a second encode pass,
which is preferable here to silently accepting inconsistent frame timing.

## Interpretation and remaining acceptance

Passing M18 establishes real ffmpeg/ffprobe final-master technical checks
and two-scene synthetic audio order on Linux. It does **not** establish:

- Mac M3 Max MLX engine/wrapper readiness or a valid private Bunny reference;
- original Arabic educational script, speech quality, or lip-sync fidelity;
- visual composition, character consistency, accessibility, child safety;
- commercial rights of model checkpoints, voices, music, or images;
- current Studio Brain Pi/Mac receipt transfer, human 11-criterion M7 QA,
  physical independent media backup or disaster recovery;
- a complete 60–90s pilot, full episode, private YouTube upload or publication.

The later **owner-authorized** single real local two-scene
«الأرنب والكرة الحمراء» pilot must still follow
`docs/M15_M16_TEST_PACK.md` and `docs/FINAL_ACCEPTANCE_M9.md`.
If every technical step passes, the result is only
`TECH_PASS_OWNER_REVIEW_PENDING`. A separate substantive owner review of
all **11 M7 criteria**, licensed-source evidence, and tested independent
backup are required before even proposing a private upload.

## CI command (for a future approved development checkout)

```sh
python -m unittest discover -s tests -p 'test_real_ffmpeg_m18.py' -v
```

No special environment variables, accounts, model files or GPU required.
No local owner-device command is being executed as part of M18.
