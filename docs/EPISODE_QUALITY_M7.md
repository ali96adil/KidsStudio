# M7 — Final Episode QA and Production Acceptance

This is development code on GitHub draft PR #28. It is NOT deployed to the
owner's Mac or Pi. No actual Chatterbox, LTX inference, paid external calls,
model downloads, upload or YouTube publishing occurred.

## Independent machine-level technical audit

The local studio-episode-qa command requires an actual private MP4 and the
exact expected SHA256 returned by the completed Studio Brain render job.
It checks:
- SHA256 equality with the render receipt.
- Exactly one H.264 video track and one AAC audio track.
- Width 1280, height 720, nominal 24fps, 48kHz audio.
- Duration 2 to 900 seconds.
- FFmpeg full decode of both selected audio and video tracks.

It writes a new, private, non-overwriting JSON technical report, status
TECH_PASS_OWNER_REVIEW_PENDING or TECH_FAILED. Even TECH_PASS is NOT a
determination about lip sync, visual quality, voice pronunciation,
educational merit, copyright ownership or publication eligibility.

Example for LATER device acceptance only, NOT to run now:

    studio-episode-qa --video /PRIVATE/episode.mp4 \
      --sha256 EXPECTED_RENDER_MP4_SHA256 \
      --report /PRIVATE/technical_qa.json

Technical report lives beside private media, outside Git. To register it
in Studio Brain running on Pi, the report must be transferred securely
to the operator host first. This branch does not automate the transfer.

## Separate human learning, artistic and rights review

Owner supplies a JSON review document with exact top-level keys:
schema_version, media_sha256, reviewer_role, criteria, summary.
Schema version 1, reviewer_role owner, summary 25–2000 characters.

Exactly ELEVEN required criteria:
1. learning_objective
2. age_appropriate_pedagogy
3. language_pronunciation
4. character_consistency
5. lip_sync_and_motion
6. audio_mix
7. child_safety
8. originality_and_attribution
9. music_voice_visual_rights
10. accessibility_and_subtitles
11. full_episode_watch

Each criterion has exactly two fields: decision and evidence. Decisions may
be PASS or NEEDS_FIX; evidence requires 20–800 characters describing what
the owner checked. Any NEEDS_FIX means CHANGES_REQUESTED and the exact
failed criterion is recorded in the series notes. No final approval.
Only 11 documented PASS criteria mark the render
READY_FOR_OWNER_EPISODE_APPROVAL, requiring a further owner approval command.

A PASS is an owner ATTESTATION, not third-party license or platform approval.

## Studio Brain commands — future manual installation phase

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite init-quality

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
      register-technical-qa colors-ar 1 --report /PRIVATE/technical_qa.json

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
      submit-human-qa colors-ar 1 --review /PRIVATE/owner_review.json

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite quality-status

Episode owner approval remains the preexisting approve-episode action.
When M7 schema is enabled, it is blocked until both technical and human QA
are registered and bound to the CURRENT render job and media SHA.
Old render revisions cannot satisfy a new render's quality evidence.

## Safeguards and remaining work

- Previous quality reports and receipts are immutable; no silent replacement.
- Quality report IDs/digests, state and passed-check totals appear in the
  existing Studio Brain system; dashboard exposes only non-sensitive summary.
- The current human review form accepts detailed owner statements but cannot
  independently establish their truth.
- M3-M6 synthetic tests remain separate from real media tests.
- Real Mac/Pi rollout, actual generated full episode, educational and
  licensing review, private YouTube preview and legacy Control Center v3
  database migration are still pending.
- Publishing and monetary API access remain completely outside this path.

The final single acceptance gate is an actual fully rendered, watched and
listened-to episode from the owner Mac, after remaining integration steps.
