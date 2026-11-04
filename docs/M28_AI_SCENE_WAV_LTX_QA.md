# M28 — independent AI voice WAV and LTX scene gates (post-PRIVATE owner review)

**Status:** Draft GitHub code and synthetic CI tests; no genuine ASR/vision
model executed by this phase on user hardware. No account connected,
video uploaded, or PUBLIC permission enabled.

## Purpose

The owner should **not listen to every WAV or approve every individual
animation scene**. The already established target is:
agent-driven production + independent internal evidence reviews →
YouTube **PRIVATE** upload → owner's one review of the complete video →
owner may APPROVE / APPROVE_WITH_NOTES / REQUEST_CHANGES.
The M24 video-level final decision remains human and per-video.

M23 and M10 legacy tests and legacy owner review commands remain
supported for compatibility. **M28 adds an optional AI-only internal
scene gate**, not a new requirement to ask the owner to listen.

## Actual M28 code

`kidsstudio/scene_ai_qa.py` + new `series_cli` commands
create an immutable `studio_scene_ai_reviews` table with:
series, episode, scene, job, script and media SHA, M23/M10 technical
report SHA, rights proof SHA, observed media data SHA, two independent
reviewer providers, decision, and timestamp.

Voice WAV review demands **all** these conditions:

- A current actual completed `voice_synthesize` Pi job and
  `PENDING_QA` stage with the exact source script SHA and WAV SHA.
- For the first-scene M22/M23 pilot, the M23 **FFmpeg PCM** WAV check
  is already registered and still pinned to that exact voice job.
  Its original `VOICE_TECH_PASS_OWNER_LISTENING_PENDING` state is
  legacy wording; here it is technical evidence **without requiring
  `--owner-listened`**.
- The **actual original scene script .txt** and **ASR transcript .txt**
  are separate private files. Their content is compared by a
  deterministic Unicode/Arabic-normalized word error rate, required
  `<= 0.10`. ASR model provider, model ID, independent job ID and
  two different further AI reviewers are recorded. The actual
  production ASR still needs an adapter that generates those files.
- A pronunciation/clarity/script-fidelity reviewer and a separate
  child-audio-safety/emotional-tone/age-appropriateness reviewer,
  each with explicit PASS/UNSURE/NEEDS_FIX and written evidence.
  Every required check must PASS.
- A separate local proof text file whose SHA matches the source-rights
  catalogue, with `commercial_youtube_kids` scope.
  Source proof existence/lineage is checked, but legal rights are
  **not adjudicated** by the software.

LTX animation review demands:

- Current completed `ltx_animate` MP4 job, exact source WAV and
  scene script SHA, already internally QA-approved voice.
- Existing registered **M10 full audio continuity** (duration,
  source voice SHA, LTX MP4 SHA, envelope correlation, lag).
- At least three timestamped **private PNG frame artifact files** with
  exact file hashes, one bounded manifest and its SHA. This verifies
  local source files, **not** that the frames were honestly extracted
  from the submitted MP4. Real frame extraction and validation against
  the source MP4 are a future qualified model-worker step.
- Separate motion/lip-sync and child-visual-safety reviewers with
  independent provider IDs, complete role-specific PASS evidence,
  plus a per-stage source-rights proof file.

The imported reviewer bundle includes a
`runner_attestation` (fixed runtime status, runner ID and
HMAC-SHA256 over the exact canonical review bundle). The verifier
requires a **32+ byte independent local runner key**, read by
the CLI from environment
`KIDS_STUDIO_SCENE_QA_RUNNER_KEY`. This blocks accidental or
unauthorized unsigned JSON and report tampering **if the key is kept
secret**. It is **not** proof that the real models actually ran, that
their reviews are correct, or that rights are legal. The trusted
worker implementation must generate this attestation **only after**
genuine ASR and multimodal reviewer inference and observation,
never at the user's request or from prefilled JSON.

The imported observation also has `model_execution_verified=true`,
as a claim from this trusted worker. Real model-connection qualification
and independent source observations still remain pending.

If any AI criterion returns `UNSURE` or `NEEDS_FIX`, or transcript
word-error rate exceeds 10%, the record is
`AI_SCENE_NEEDS_FIX`, a Studio Brain note is created, and
the stage remains `PENDING_QA`. No new LTX stage is unlocked.
A valid `AI_SCENE_READY_PRIVATE_ONLY` receipt may be
`auto-approve-scene-stage`d internally; it sets the existing
`QA_APPROVED` state with an unmistakable marker indicating
**AI internal readiness, owner will review after PRIVATE upload**.
No PUBLIC or owner video approval is ever recorded.

## New CLI (future local use; not executed on devices)

Initialize M28 once on Pi Studio Brain (after M13/M23 initialization):

```sh
python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite init-scene-ai-qa
```

A **trusted model worker**, with the secret key protected on the
worker, first generates the ASR, frame extraction, rights catalogue
and two different AI reviews; it signs the exact bundle. Import that
bundle on the Pi (do not invent model runs or manually set PASS):

```sh
python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
  register-scene-ai-qa colors-ar 1 1 \
  --stage voice_synthesize \
  --report /PRIVATE/m28_signed_review.json \
  --observations /PRIVATE/m28_asr_observations.json \
  --rights /PRIVATE/m28_rights_proof.json
```

After a verified PASS:

```sh
python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
  auto-approve-scene-stage colors-ar 1 1 --stage voice_synthesize
```

Then queue LTX using the existing M13 scene command, register
M10 continuity and the signed LTX visual review, and run the same
auto-approve command with `--stage ltx_animate`.

**None of these commands uploads or publishes video.** The user can
continue using the original manual path during the migration.

## CI evidence and remaining blockers

M28 tests generate an **actual PCM WAV** and run actual FFmpeg/FFprobe
technical decoding. They also use **FAKE ASR transcripts and fake
AI HMAC-signed reviewer reports**, clearly labelled as fixtures:
pass without `owner-listened`; reject absent model-runner key,
tampered signature, duplicate provider, fabricated rights scope,
bad transcript/word errors, altered media SHA, missing frames,
wrong M10 report and repeat QA. They do not prove the quality
of an AI reviewer or produce real animated video.

- **Real ASR and image-language models still need to be connected,
  independently observed and qualified.** No real model was run here.
- M28 pilot WAV technical gate is currently M22 **scene 1 only**;
  broad multi-scene WAV technical registration for all scenes remains.
- Existing owner script approval, owner-issued first pilot and any
  separate M6 stage QA remain legacy gates. The next changes must
  replace these with trustworthy AI approval flows without bypassing
  real content or legal rights verification.
- The HMAC key must never be placed in GitHub, documentation or UI;
  its presence is a prerequisite, not an automatic inference.
