# Character Factory v0.1 — first end-to-end production slice

**Does real work on a Mac where ComfyUI Desktop is running.** The service on
GitHub Actions cannot access the owner's Mac. It deliberately does **not**
generate copyrighted/reference artwork in the public repo.

## What it now does
1. Reads a versioned rig-first blueprint defining ten independent bunny layers.
2. Confirms one **API-format** ComfyUI workflow matches the approved local
   SHA-256, node-class allowlist and checkpoint allowlist.
3. Runs **each part** with its own descriptive prompt and output prefix, in
   a **sequential batch** on the Mac's local ComfyUI server.
4. Collects the actual generated PNG from ComfyUI's job history and output
   API and records the job id, model list, workflow digest, prompt digest and
   SHA-256 of each collected image.
5. Requires genuine RGBA transparency, matching dimensions and separate
   nonempty layers. Rejects a conventional opaque diffusion image rather
   than pretending the background disappeared.
6. Produces a rig.json, an animated motion_preview.gif with six test actions,
   motion_contact_sheet.png and a factory_report.json on local storage.
7. Stops with an explicit failure report when inputs are missing/unsafe,
   ComfyUI fails, transparency fails or the technical QA fails.

**Technical success = NEEDS_INDEPENDENT_VISUAL_REVIEW**, unless the optional
independent **local vision-model reviewer** is explicitly configured.
Visual review uses a separate multimodal model through local Ollama
(`http://127.0.0.1:11434`), examines the motion contact sheet, optionally
compares a canonical character image, and returns PASS / REVISE / FAIL with
reasons, confidence and evidence. It cannot override technical QA, and checks
hashes to reject stale snapshots. A low-confidence PASS or any medium/high
reported defect is automatically downgraded to REVISE. Publication still
requires human owner approval. Visual model evaluations are probabilistic and
can miss defects; no model has been installed or validated on the Mac yet.

## First real Mac run (not necessary before complete integration review)

ComfyUI Desktop must be open in local mode at `http://127.0.0.1:8188`.
Export your known-good **API format** workflow, locate its text and
SaveImage nodes, and approve a local profile per [ComfyUI adapter guide](COMFYUI_ADAPTER.md).

IMPORTANT: To produce individual transparent layers, the approved workflow
**must have a real transparency node/output**, or per-part generation will
correctly stop at NO_ALPHA. A plain FLUX.2 text-to-image workflow often emits
opaque RGB despite prompts mentioning transparent backgrounds.
Avoid the FLUX.2 FP8 checkpoint on Apple MPS, as earlier local work failed.

Optional plan only (makes no request):

    kidsstudio plan-rig examples/bunny_blueprint.json --output /tmp/bunny_plan.json

Production batch, only after a vetted transparent-output workflow is available:

    kidsstudio build-character examples/bunny_blueprint.json \
      --workflow /safe/local/workflow_api.json \
      --profile /safe/local/comfy_profile.json \
      --out /safe/local/characters/bunny/v02 \
      --execute

Output directory must not already exist; one new version per run. Keep
outputs OUTSIDE GitHub. Check `factory_report.json` before considering any
asset for production. Use `kidsstudio motion-preview /safe/local/characters/bunny/v02/rig.json --out /safe/local/review_again`
to re-render evidence if manifest or parts are intentionally revised.

## Security and limits

- Only the loopback ComfyUI API is permitted; no proxies or redirects.
- An explicit `--execute` is required, and checkpoints remain manually pinned.
- No implicit model downloads, paid API calls, remote inference or cloud uploads.
- No auto-retries, so one bad transparent layer aborts without burning through 10 model runs.
- The current adapter assumes a standard CLIPTextEncode text node and SaveImage node.
- No automated generation of hidden joint geometry is guaranteed by a diffusion model.
- No current image-conditioned identity preservation or independent vision agent.

## Next integration

Use identity-conditioned generation and a verified transparent-output workflow;
add retry/repair bounded by quality evaluation and budget caps; then add a
genuinely independent visual QA agent using the rendered preview and evidence.

## Optional independent visual reviewer

After producing a successful rig, with an **already installed** local
multimodal Ollama model (no models are downloaded automatically):

    kidsstudio visual-review /local/characters/bunny/v02/rig.json \
      --evidence /local/characters/bunny/v02/review/motion_evidence.json \
      --reference /local/characters/bunny/v01/bunny_neutral_v01.png \
      --model YOUR_INSTALLED_VISION_MODEL \
      --out /local/characters/bunny/v02/visual_review.json \
      --execute

Or supply `--review-model YOUR_INSTALLED_VISION_MODEL` to `build-character`
to invoke this reviewer after rendering the contact sheet, in the same run.

In the case of any review service failure or invalid model response the
pipeline FAILS CLOSED, preserves the collected assets, and records the failure.
Regenerate visual evidence after any edit to layer images.

## Locking original character identity

For the next bunny production run, add a canonical reference image in the
ComfyUI workflow with an approved `LoadImage` node feeding the final output,
then include `reference_node_id` in the local profile. Run:

    kidsstudio build-character examples/bunny_blueprint.json \\
      --workflow /safe/local/reference_workflow_api.json \\
      --profile /safe/local/reference_profile.json \\
      --reference /safe/local/bunny_neutral_v01.png \\
      --review-model YOUR_INSTALLED_LOCAL_VISION_MODEL \\
      --out /safe/local/characters/bunny/v02 \\
      --execute

This submits the original character PNG only to the local ComfyUI process,
records its hash and feeds the same reference into all individual jobs.
The independent local vision reviewer also receives this reference and
must flag visible inconsistent proportions, expression and colors.

Both the reference workflow and local multimodal reviewer still require real
Mac setup before autonomous art production can be claimed.

## v0.2 retry orchestration

The separate `produce-character` command (see
[PRODUCTION_CYCLE.md](PRODUCTION_CYCLE.md)) adds bounded rejection/repair
handling. The plain `build-character` command still produces a single
attempt only. Repair attempts are independent version directories and cannot
overwrite the original layers.

## v0.3: Anatomical placement quality gate

The bunny blueprint now declares an anatomical `expected_region` for every
rig layer (body, head, ears, eyes, mouth, both arms and legs). In its
`qa_policy`, `strict_parts=true` requires all parts to be assigned a region.
The code measures actual alpha coverage, not just transparency-mode labels:

- Reject if too much visible alpha lies outside the permitted region.
- Reject near-empty layers or tiny dots masquerading as character limbs.
- Reject identical RGBA images appearing under multiple part filenames.
- Reject missing/malformed geometry policy or part bounds.
- Abort on the **first generated bad part**, before sending a request for the
  next layer, reducing wasted diffusion work.

The bunny's regions are **generous approximate coordinates** from the existing
1024 × 1024 reference drawing and require calibration with real generated
layers. The constraints measure anatomy registration only; they cannot detect
all shoulder seams, art-style drift, hidden connector quality, or true rig
deformation. A successful technical pass still requires independent visual QA.

`qa_policy` is optional for older manifests, where technical QA remains
backwards-compatible. New production characters should use strict mode,
whose upper bounds are intentionally conservative and tuneable per character.

### Required blueprint fields

    {
      "qa_policy": {
        "strict_parts": true,
        "max_outside_fraction": 0.18,
        "min_inside_fill_fraction": 0.003,
        "alpha_threshold": 32,
        "reject_identical_layers": true
      },
      "parts": [
        {
          "id": "arm_right",
          "expected_region": [560, 517, 765, 791],
          "pivot": [621, 570]
        }
      ]
    }

Other required blueprint fields are omitted from this illustrative excerpt.

## Before the first real FLUX bunny run

Run the **offline production graph audit** from [WORKFLOW_READINESS.md](WORKFLOW_READINESS.md) with the owner's real local ComfyUI workflow, profile and original bunny PNG. An unmodified text-to-image graph or reference image wired straight to SaveImage will now be blocked by the production CLI and Mac media worker. This is intentionally distinct from visual QA: a wired graph does not guarantee good transparent layers or stable joints.

The two-part `probe-bunny` command is the first live Mac qualification gate; it only generates body and right arm and requires visual review before authorizing the full 10-part Character Factory. See [WORKFLOW_READINESS.md](WORKFLOW_READINESS.md).
