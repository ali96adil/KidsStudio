# M37 — synchronized private audiovisual review and M10/M28 Pi import

**Status: DRAFT branch / NOT installed or qualified on owner Mac/Pi.** GitHub CI uses real FFmpeg, 3-second synthetic modulated WAV and a sound-bearing H.264/AAC MP4, but both independent reviewer executables are **MOCKS with no trained perception**. Tests do not show actual lip-sync, speech correctness, video quality, originality or legal rights.

## Implementation

1. `studio-synchronized-av-review` reads and SHA-pins the exact original scene WAV, synchronized MP4, original script TXT, rights-source JSON and an M10 report. It invokes **real FFmpeg PCM decoding of BOTH audio sources** via `compare_voice_to_a2v` and requires its complete deterministic results to match the frozen current M10 report. It independently extracts 3–12 real PNG frames using FFmpeg.
2. Two separate *owner-installed* audio/video-capable executable adapters with distinct SHA-pinned local binary and checkpoint files are each invoked with the original **audio-bearing MP4, WAV, script, sampled-frame manifest and model checkpoint**. `motion_sync` checks lip-sync, voice-continuity and character motion; `visual_child_safety` checks age appropriateness, visual consistency and unsafe content. An adapter without actual simultaneous AV perception **must return UNSURE**, never PASS. Test fakes merely exercise schema, source binding and process isolation.
3. Bounded, role-specific JSON replies must pin MP4/WAV/script/frame-manifest/model hashes. Any absent audio track, corrupted media, changed model, wrong provider identity, missing evidence, or failed subprocess stops. The worker produces an immutable `observations.json`, HMAC-signed model-executable/checkpoint lineage, and an independently HMAC-signed **M28 candidate**; this is neither owner review nor public permission.
4. `studio-import-synchronized-av` is read-only by default. With explicit `--execute`, it checks the **current Pi LTX job**, current approved voice, scene script, exact signed evidence, M10 and rights files. It registers M10 once (including compatibility with M36 earlier registration), then calls M28's independent validation and, only with all criteria PASS, advances that one LTX stage to `QA_APPROVED` for PRIVATE internal production. NEEDS_FIX remains pending for bounded M31 repair; any UNSURE also remains blocked. Matching replays are idempotent, mismatched prior reports are refused. No user-facing owner review is impersonated.
5. The existing M36 still-frame-only candidate remains blocked on lip-sync. M37 creates a **new, separate** signed report after actual synchronized AV adapters evaluate the same current job. The read-only Arabic dashboard automatically stops counting that LTX job as pending AV proof after internal stage approval. No YouTube publish route exists here.

Both model subprocesses and FFmpeg inherit only allowlisted non-secret environment variables, not OAuth or HMAC credentials. HMAC authenticates the report **source** assuming the signer key remains private; it does NOT prove the checkpoints really understand audio/video. This is a mandatory external qualification requirement, not a claim that the software alone enforces model competence.

## Commands (future private pilot, **not** run on owner's hardware)

`studio-synchronized-av-review --help` describes the explicit private SHA-pinned media, FFmpeg, reviewer binaries/checkpoints, two provider names, runner secret and unique output directory. It defaults to no media/model execution; opt in with `--execute`. Then:

```sh
studio-import-synchronized-av \
  --db /PRIVATE/studio.db --series colors-ar --episode 1 --scene 1 \
  --report-dir /PRIVATE/reviews/scene01_m37 \
  --m10-report /PRIVATE/reviews/scene01_m10.json \
  --rights /PRIVATE/scene01_ltx_rights.json
```

Default import is also read-only; `--execute` requires the **identical worker-secret** `KIDS_STUDIO_SCENE_QA_RUNNER_KEY` loaded from owner-controlled private configuration. Never embed original video, prompts, secrets or actual checkpoint weights in GitHub.

## Exit gate before one full hardware test

CI must pass on Python 3.11 and 3.12, including a synthetic two-scene Pi production-cycle and real FFmpeg media assembly (M17/M18/M33). Qualified real audio-capable reviewer checkpoints must be identified, calibrated on success/failure clips and locally installed; runtime Pi/Mac worker receipts, external rights provenance, full-final private QA and Google PRIVATE OAuth still require practical qualification. The owner reviews an already uploaded **PRIVATE** video and can accept, accept with notes or reject; AI reviews do not make that video public.
