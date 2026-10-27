# Bounded autonomous character production v0.2

This milestone is a production **orchestrator**, not proof that the existing
FLUX.2 workflow can generate perfectly aligned rig parts. It builds on the
already-written local ComfyUI connector, independent vision QA and Godot export.

## Behavior

1. Require the known original character PNG as the canonical identity reference.
2. Validate approved workflow checksum and a real **connected** LoadImage
   reference node before making output folders or model requests.
3. Launch an initial full rig generation: separate PNG for each part.
4. Reject missing transparency, broken parts and invalid geometry immediately.
5. Render six diagnostic motions; ask a separate local multimodal model for
   PASS / REVISE / FAIL, with concrete defects and responsible part_id.
6. On **PASS**, label the attempt `INTERNAL_ASSET_APPROVED_NOT_FOR_PUBLICATION`.
7. On **REVISE** with explicit valid per-part defects, copy previously approved
   technical source layers into a new attempt, regenerate **only** rejected
   parts with bounded defect descriptions, and rerender/review.
8. On **FAIL**, stop. On ambiguous or multi-part review with no credible
   culprit, **BLOCKED_MANUAL_TRIAGE**; do not guess an edit. Never retry
   indefinitely or silently accept a poor result.
9. Defaults: maximum **2 attempts**, maximum **3 regenerated parts per
   revision**. Absolute bounds: max 3 attempts, max 4 repair parts.
10. Preserve attempt_01, attempt_02 and the machine-readable audit log
    `production_cycle.json`. Every collected/reused part carries a SHA256.

This is intentionally conservative. A review that reports a shoulder seam
but cannot clearly attribute the defect to one layer cannot trigger random
regeneration of every character part.

## Command

    kidsstudio produce-character examples/bunny_blueprint.json \
      --workflow /local/approved/workflow_api.json \
      --profile /local/approved/comfy_profile.json \
      --reference /local/private/characters/bunny_neutral_v01.png \
      --review-model YOUR_INSTALLED_LOCAL_VISION_MODEL \
      --max-attempts 2 \
      --max-repair-parts 3 \
      --out /local/private/renders/bunny_cycle_001 --execute

Do not store outputs, large models, original character masters or service
credentials in the public GitHub repository. The output folder must be NEW,
outside any Git repository. No background work on the Mac starts until a
local operator **explicitly** invokes this command; it does not grant agents
autonomous perpetual host access.

## Quality and safety

The resulting status is a **production asset** judgment, **never YouTube
publication approval**. Film/episode/audio/bilingual/safety review must be
separate; owner approval remains required for a public upload.

The vision reviewer is probabilistic and can miss visual defects. A single
PASS on a contact sheet is not equivalent to human professional art approval.

The loop has **no paid/cloud API fallback**, no autonomous checkpoint
downloads, no unbounded retrying, and no automatic upload to YouTube.

Offline CI tests use fake ComfyUI and fake vision models. We have NOT
validated this v0.2 against real isolated character parts on the Mac.
