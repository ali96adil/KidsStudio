# M36 — Signed M29 visual evidence → current Pi M10 import (fail closed on silent-frame lip sync)

**Status:** GitHub DRAFT software, no user Mac/Pi or YouTube access. Real FFmpeg frame extraction in CI, but mocked Ollama models and **synthetic M10 envelope receipts**. Never treat CI as trained vision/audio quality evidence.

## The problem discovered before the integrated hardware test

M29 samples real video frames into PNGs for two separate Ollama vision roles. Still frames reveal character poses/visual safety; they **cannot establish audible narration identity, voice continuity, or actual lip synchronization**. Earlier M29 instructions told the models to say UNSURE on those, but signing code did not independently enforce it. A confident, wrong vision model might have produced a signed all-PASS, which existing M28 importer could accept. M36 blocks that false success.

- `sign_after_m10` now rejects model-output PASS on `lip_sync` or `voice_continuity` from the M29 silent-frame worker. A real synchronized audio/video-capable independent reviewer is required for those criteria.
- `studio-import-visual-review` checks the exact existing signed M29 report, M10 receipt and owner-rights source, verifies HMAC, matches the **currently completed Pi LTX job**, active scene script, **already-approved voice SHA**, current media SHA and current private M10 source.
- The default command is read-only. `--execute` registers only the exact M10 technical continuity receipt in the current Pi database, once; an exact replay is harmless. It also writes a per-current-LTX-job immutable, private `AV_AUDIO_REVIEW_REQUIRED` observation, and the read-only Arabic dashboard shows how many scenes still need synchronized audio/video AI review. This observational entry is not a signed final M28 acceptance and does not trigger a repair. Changed data, stale episode/job, wrong signing key, paused studio or a differing previously registered M10 receipt all block.
- Because this report is based solely on silent frames, M36 refuses to import an incomplete visual report as a signed *final* M28 verdict. It leaves LTX in `PENDING_QA`, explicitly reports missing audio-informed lip-sync and voice-continuity evidence, and queues **no M31 repair** for an `UNSURE` reason. Spending GPU time rerendering identical scenes would not supply the missing evidence.
- All completed original M29 files remain available in private storage for a subsequent qualified AV reviewer. Only an actual synchronized-audio and video reviewer whose independent abilities are qualified can produce future full M28 review evidence. The owner still decides on each already-uploaded PRIVATE episode; nothing makes a video PUBLIC.

## Future private-Pi operator invocation

```sh
studio-import-visual-review \
  --db /PRIVATE/studio.db --series colors-ar --episode 1 --scene 1 \
  --report-dir /PRIVATE/reviews/scene01_ltx_attempt001 \
  --m10-report /PRIVATE/reviews/scene01_m10.json \
  --rights /PRIVATE/scene01_ltx_rights.json
```

Read-only by default; add `--execute` to register the current M10 receipt only. Parent environment must contain `KIDS_STUDIO_SCENE_QA_RUNNER_KEY` from a private owner-controlled secret manager. This tool never invokes models or uploads anything.

## Tests and remaining exit criteria

M36 tests prepare an AI-approved synthetic scene voice via M35, queue/complete a current Pi LTX job, capture **real** FFmpeg frames from a synthetic MP4, call mock local vision adapters, sign with the exact synthetic M10 SHA and attempt import. They check no M28/PUBLIC approval, idempotent M10 receipt, rejects wrong HMAC, changed M10, paused queue and a forged lip-sync PASS that is even HMAC-signed. The standalone M29 signing check likewise rejects silent-frame PASS.

**Next required before complete software acceptance:** synchronized *actual* audiovisual perception (two independent audio/video-capable checkpoints or an auditable equivalent), test two-scene voice+animation+assembly+final QA end-to-end with exact receipts and bounded repair, then real installed models and Mac↔Pi authenticated hardware qualification. YouTube OAuth PRIVATE-only, owner post-upload review and explicit independent public publishing stay separate.
