# M17 — Real FFmpeg Audiovisual Integration on CI

Status: development code only, draft PR #28. No owner Mac/Pi installation,
real AI model inference, paid APIs, private-media upload, or YouTube activity.

## Motivation

The M4 FFmpeg assembly and M6 MediaExecutor tests previously used fake
media bytes and fake subprocess runners. Those tests establish queue/state
logic, but cannot prove real video codecs, audio stream mapping, filter
syntax, normalization, concat output or final output duration.

## Three non-AI, REAL multimedia tests

The new tests/test_real_ffmpeg_m17.py and updated GitHub Actions workflow
explicitly install FFmpeg/FFprobe on the temporary Linux CI runner.

1. Synthesize a 384x384 red scene and a 384x384 blue scene, each 1.2 s
   with exactly one synthetic tone as its audio track. Hash-pin the
   sources, execute the ACTUAL EpisodeAssembler with the ACTUAL ffmpeg,
   normalize to 1280x720 at 24fps, concatenate to a playable MP4, and
   verify streams, duration, final SHA256, private QA report, source
   immutability and same-run-ID no-overwrite semantics.
2. Generate a synthetic video that has NO audio; the REAL ffprobe must
   reject it before M4 creates any render folder.
3. Invoke REAL MediaRecipes and MediaExecutor.execute with one
   short scene, and verify the returned MP4 SHA, type, byte count,
   pending-human-review status, and immutable-job-ID guard.

FFmpeg/FFprobe are mandatory in this CI; missing tools are test failures,
not silent skips. All source media is created on the CI runner inside
temporary private test directories and removed afterward. No original
Bunny artwork, voice samples, proprietary models or secrets are used.

## Limits

These clips are solid colors and machine-generated tones, NOT real
Chatterbox/LTX audiovisual media, original educational stories or lip-sync.
Passing the M17 test proves actual FFmpeg syntax, container/stream mapping,
filter and private media worker output on a LINUX CI runner, but NOT:
- functioning Apple Silicon MLX wrappers or original voice reference;
- Bunny animation quality, realistic mouths, child-safe creative content;
- copyright/model/voice/music licensing or final pedagogical benefit;
- an approved real full-length episode, independent backups or uploads.

After all code gates pass, the owner-authorized Mac/Pi end-to-end pilot still
follows docs/M15_M16_TEST_PACK.md and requires explicit independent QA.

Local source checkout test commands for later approved development:

    python -m unittest -v tests.test_real_ffmpeg_m17
    python -m unittest discover -s tests -v

PR remains draft and unmerged. No deployment to user devices.
