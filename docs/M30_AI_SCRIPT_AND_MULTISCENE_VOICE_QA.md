# M30 — Independent internal AI script gate + voice QA for all scenes

**Implementation scope: draft GitHub PR #28, not deployed.** No real user
AI calls, no owner media copied, no YouTube upload or PUBLIC permission.
Python CI uses synthetic model responses and real FFmpeg test WAV.

## Operational goal

Protect the user's attention: the studio should create educational
series in sequence, and independent internal agents should review
scripts, narration and animation. The owner should only watch the
finished YouTube **PRIVATE** video and issue the post-upload final
APPROVE / APPROVE_WITH_NOTES / REQUEST_CHANGES decision.

## M30 new code

`studio-review-script-ai` is an explicit, **opt-in** local command.
It reads the current Studio Brain `OWNER_SCRIPT_REVIEW` episode,
the completed `script_draft` and independently completed
`editorial_review` jobs (including their exact parent/child
receipt and source hash), then reads the actual owner-private
`answer.txt` from the model worker's source directory.
The SHA must match the current episode state.

It calls **two further real, independently configured
`ChatRouter.complete` model providers**, excluding the original
writer and all already selected reviewers. The two reviewers must
have **different model IDs and distinct endpoints**, not simply
different user-defined aliases. The normal router requires
explicit preconfigured providers, secrets only via environment,
HTTPS (except loopback), and **free-only billing by default**.
Nothing quietly selects a paid remote model or reuses the writer.
The existing first editorial job is verified for provenance,
but its unstructured output does **not** substitute for either
of the two additional independent structured QA reports.

Both reviewing models receive the full original script, language
and specific learning objective. Each must produce strictly valid
JSON with evidence for these exact criteria:

- learning objective
- age appropriateness
- factual accuracy
- language quality
- narrative originality
- child safety

Each criterion is PASS / UNSURE / NEEDS_FIX. A final private-only
internal `SCRIPT_APPROVED` transition is allowed **only when
both complete, distinct reviewers returned PASS for all six**.
The episode records
`SCRIPT_APPROVED_BY_TWO_INDEPENDENT_AI_PRIVATE_ONLY` in the
durable audit trail, not `SCRIPT_APPROVED_BY_OWNER`.
UNSURE/NEEDS_FIX leaves the episode needing revisions, with
a concrete Studio Brain note and immutable output receipt.
Every exact episode/revision can only be submitted once:
no silent duplicate submissions and no stale approval when
the episode/source SHA changes during model calls.

This is **a model opinion**, not a proof that a script is factually
correct, safe or sufficiently original for commercial use.
M27 later source-rights tracking and the owner's final
post-PRIVATE review remain separate and mandatory.

## Multi-scene narration

The M23 existing real FFmpeg WAV technical report importer now
handles **all regular M13 `voice_synthesize` scene jobs**,
not just the original M22 scene-one pilot. For a M22 pilot,
the pilot marker remains tied to scene 1. Ordinary subsequent
scene jobs carry no pilot marker, but still must satisfy:

- current Pi job completed with `VOICE_RENDERED_PENDING_QA`
- current, matching scene script SHA and exact WAV SHA/bytes
- real FFmpeg/FFprobe WAV tech report, full checks PASS
- one immutable report per exact voice job, no overwrite

A separate M28 signed AI scene reviewer continues to be
required before the internal **AI** approval pathway may progress
to LTX. This is technical evidence, not a language/rights verdict.

## Pilot scheduling without owner notes

The new `queue-first-voice-ai` command allows the first
two-scene pilot only when a **current M30 independent AI**
`AI_SCRIPT_PRIVATE_READY` receipt exists for the same episode
revision/script SHA, the series is active, the immutable scene
plan SHA matches, the queue is not paused, and no prior pilot
already exists. An ordinary old owner-approved script still
uses the legacy `queue-first-voice-pilot` action.
No false owner audit is created in the new pathway.

## Commands (future local Mac/Pi setup only)

Once the normal Studio Brain agent has prepared a draft and
completed the first editorial review, configure **at least three
distinct model providers** (writer plus two reviewers), with
review routes including two independent, different endpoints
and model checkpoints. Then, on the coordinator's authorized
local machine:

```sh
studio-review-script-ai \
  --db /PRIVATE/studio.sqlite \
  --providers /PRIVATE/model_providers.json \
  --artifacts /PRIVATE/ai_worker_artifacts \
  --series colors-ar --episode 1 --language ar \
  --objective "Recognize a red object" --execute
```

This is a real model operation only after explicit local
setup; the GitHub tests use deliberately fake model responders.

After creating a matching, immutable two-scene plan:

```sh
python -m kidsstudio.series_cli \
  --db /PRIVATE/studio.sqlite queue-first-voice-ai \
  colors-ar 1 \
  --recipe scene_one_local_voice \
  --plan-sha256 EXACT_CURRENT_PLAN_SHA256
```

For each completed regular voice job, inspect the actual WAV
using M23 FFmpeg and register its report:

```sh
python -m kidsstudio.series_cli \
  --db /PRIVATE/studio.sqlite register-scene-voice-qa \
  colors-ar 1 2 --report /PRIVATE/scene02_voice_tech.json
```

The M28 independently signed audio/child-safety evidence importer
still has to run for each scene before `auto-approve-scene-stage`.
No owner per-scene listening is needed on this AI pathway.

## Release candidate status

**Not hardware test ready.** M30 provides a functioning _contract_
for real independent text model calls and multi-scene technical
voice QA; CI only validates the protocol, source hashes and
state transitions against fake models, plus real WAV decoding.

Before the single integrated Mac/Pi qualification we still need:
- actual separate model inference adapters for **audio** judgment
  (ASR alone cannot establish emotional tone, speaker identity or
  child suitability);
- robust scene regeneration after unsure/needs-fix and automatic
  orchestration of scripts/assets/voice/LTX/assembly;
- one integrated synthetic, full two-scene production acceptance
  test, and a single truthful command to run it;
- real Mac deployment and OAuth qualification afterwards.

See [M29 test entry requirements](M29_REAL_LOCAL_MEDIA_MODELS_AND_TEST_ENTRY.md).
No PUBLIC endpoint or owner-post-private decision is altered.
