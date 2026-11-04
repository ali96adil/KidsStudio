# M27 — Independent AI internal final QA; owner reviews after PRIVATE upload

**GitHub Draft PR #28; NOT deployed, no real model/video/YouTube execution.**
M27 is an **opt-in migration for final-episode M7/M8 approval**, not a
declaration that all internal human signoffs have been removed.

## Requirement

The Kids Studio owner wants agents to produce, review, improve and
upload each finished episode **PRIVATE**. The owner then watches the
whole video on YouTube and chooses **APPROVE**,
**APPROVE_WITH_NOTES**, or **REQUEST_CHANGES**, with timestamped
feedback. Internal audio or frame-by-frame approval requests
should not block the owner's attention repeatedly.

## M27 implemented gate

For the final assembled MP4, the old owner-authored M7 subjective
report can be replaced **only on M27 paths** with three distinct
independent evidence sources:

1. An actual current M7 technical FFmpeg report, tied to the exact
   completed final render job and SHA256, with all ten technical checks
   passed. M27 will **not** create a fake technical report.
2. Two AI reviewer output reports in one immutable private bundle:
   **`pedagogy_language`** (learning objective, pedagogy, pronunciation,
   captions/accessibility, originality/attribution) and
   **`visual_child_safety`** (character consistency, apparent
   lip-sync/motion, audio mix, child safety, whole-episode watch).
   Their provider identifiers **must differ**, their criteria must
   be complete and their evidence must reference the **same** exact
   final MP4, approved script, and audio/transcript/frames manifest.
   `PASS`, `UNSURE`, `NEEDS_FIX` are allowed judgments, but
   **only every criterion PASS** can unlock the PRIVATE queue.
   Any UNSURE/FIX records a triage note and blocks finalization.
3. A separate asset-rights provenance catalogue containing a digest
   for every source asset and its underlying recorded proof,
   classification as original/appropriately licensed/public domain,
   explicit commercial YouTube Kids scope, and a claim that all
   inputs are accounted for. AI free-text claims are **not** a substitute
   for this catalogue. The current importer checks structure,
   cross-source digest consistency and declared scope; it does
   **not authenticate the ownership/licence proofs against external
   registries or adjudicate law**. Missing/uncertain documentation
   must block and escalate, not be magically certified by AI.

Both reviewer entries include an `evidence_sha256` and an explicit
`release_approved=false` value. Neither the reviewer bundle nor its
PASS decision authorizes PUBLIC or scheduled publication.

This is a provenance validation gate for future independent,
multimodal agent adapters. At M27, **the project does not yet
execute a genuine audiovisual AI reviewer end-to-end** or prove that
an AI genuinely watched/understood every frame; the tests use
synthetic reports. A provider name supplied in JSON can be forged.
Actual provider-attested reviewer invocations and evidence extraction
are a next integration milestone.

## New states / compatibility

- `AI_INTERNAL_READY_PRIVATE_ONLY`: current completed MP4, M7 tech
  QA, two distinct providers with complete PASS results, the
  transcript/frames/audio manifest, and source-rights catalogue
  match. **Internal readiness only**.
- `AI_INTERNAL_CHANGES_REQUIRED`: a real criterion reports
  UNSURE or NEEDS_FIX, preventing any internal ready transition.
- `EPISODE_APPROVED` remains the legacy internal episode state;
  M27 records distinct audit event
  `M27_AI_INTERNAL_READY_OWNER_REVIEW_AFTER_PRIVATE_ONLY`
  and note `AI_INTERNAL_PRIVATE_ONLY_NO_OWNER_VIDEO_REVIEW`.
  This is NOT a statement the owner reviewed the video.
- The M8 immutable archive now accepts exactly **one** of
  `owner_qa` (legacy) or `agent_qa` (M27), alongside episode
  master, approved script and technical QA, with exact hash match.
- M8 still generates the old
  `READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED` status for
  downstream M25 compatibility, but adds
  `owner_final_qa=false` and
  `ai_internal_review_approved=true` in M27 mode.
  M25 verifies exactly one of those two approval paths before
  starting the **PRIVATE-only** upload. M26 requires current
  matching M27 reviewer records and 11 internal QA criteria passed.
- M24 owner-review decisions remain mandatory **after** YouTube
  PRIVATE upload. M27 does NOT provide an owner approval for a
  YouTube PUBLIC change.

The older M7/M8 owner QA path and its tests stay supported.
No old approved episode is silently migrated to AI mode.

## Commands (future private Pi/Mac testing only)

On Pi, after ordinary M7 QA schema is initialized:

```sh
python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite init-ai-final-qa
```

After real technical QA and two independent external model reviewers
have produced appropriately bounded JSON **outside Git**, import
their immutable evidence files:

```sh
python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
  register-ai-final-qa colors-ar 1 \
  --bundle /PRIVATE/m27_two_reviews.json \
  --observed-evidence /PRIVATE/m27_observed_audio_frames.json \
  --rights /PRIVATE/m27_asset_rights.json
```

If every criterion passed and rights source evidence is registered:

```sh
python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
  finalize-ai-private colors-ar 1
```

Then create the regular immutable M8 archive using
`agent_qa` in place of `owner_qa`, export current M8
readiness, and allow the standing policy M26 PRIVATE uploader
to queue the current master. Owner M24 post-upload review remains
separate and explicit.

## What remains before an unattended real production line

- Actual multimodal reviewer execution by independent, qualified
  vision/audio/text models, not manually crafted JSON claims.
- Generate/prove the actual transcript, sampled frame manifest,
  audio-analysis evidence from real MP4 and make those artifacts
  verifiable against the stored SHA rather than merely trusting
  declared JSON digests.
- Formal asset/source rights registry with independently checked
  source proofs and escalation for ambiguities.
- Replace remaining **M13/M23 scene-level owner signoffs, M10 audio
  subjective approval, and script-owner QA** with verified independent
  agent gates. M27 updates **final-episode internal QA first**.
- Validate the whole device + Google OAuth PRIVATE flow on the Mac/Pi.
  There is NO permission here to publish a video PUBLIC.
