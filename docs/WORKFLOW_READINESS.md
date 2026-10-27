# Character Workflow Production Readiness

This is an **offline gate**, not an image-generation or artistic acceptance test.
KidsStudio's earlier ComfyUI checks could mistakenly accept a graph in which
`LoadImage` was connected to `SaveImage` but never conditioned the sampler.
That produces a false impression of reference-locked rig art.

## Approved graph contract

In the **private**, SHA-256-pinned ComfyUI API workflow profile, add:

```json
{
  "production_contract": {
    "conditioning_node_id": "REPLACE_WITH_REAL_NODE_ID",
    "sampler_node_id": "REPLACE_WITH_REAL_NODE_ID",
    "matting_node_id": "REPLACE_WITH_REAL_NODE_ID"
  }
}
```

This is an excerpt; the profile also requires its existing
`approved_workflow_sha256`, `prompt_node_id`, `reference_node_id`,
`filename_node_id`, allowed node classes and approved model filenames.

The specific node IDs are **not** guessed or generated: they must match
nodes in the approved local workflow *exported using ComfyUI API format*.

The audit verifies these data dependencies exist in the actual graph:

```
Canonical LoadImage ─→ Image conditioning ─┐
                                         ├→ Sampler → Decode → Alpha/matting → SaveImage
Part-specific CLIPTextEncode ─────────────┘
```

The final image **must** be saved from the downstream alpha/matting path.
The reference may not merely be composited after sampling, and the text
prompt may not bypass the sampler. Cyclic dependencies fail closed.

Production must separately prove that a suitable installed alpha-producing
node produces actual transparent parts, that reference conditioning has a
strong **visual** effect, and that joints overlap cleanly. The graph is a
wiring contract only. Node classes alone don't certify their semantics;
the profile is approved by an operator after inspecting the exact node.

## Completely offline Mac check, without GPU calls

```sh
kidsstudio audit-character-workflow examples/bunny_blueprint.json \
  --workflow /local/private/workflow_api.json \
  --profile /local/private/workflow_profile.json \
  --reference /local/private/bunny_neutral_v01.png
```

Success produces `GRAPH_READY_NOT_GENERATED` plus the workflow checksum,
reference checksum, recorded node classes and output SaveImage ID. It never
contacts the running ComfyUI instance or uploads the source drawing.

Production paths `kidsstudio build-character --execute`,
`kidsstudio produce-character --execute` and the pinned Mac
`character_generate` media worker run this audit **before** generating.

## Exact result selection

History data uses output node IDs. KidsStudio now reads **only** the approved
`SaveImage` node from `/history/{prompt_id}` after ComfyUI indicates
completion. It requires **exactly one** output PNG per rig-part job. It will
not silently select a preview, background image, or alternate SaveImage.

## Current limits

- The user's full live FLUX.2 Klein + reference + isolation + alpha workflow
  has not been collected, inspected or validated on the Mac.
- The reference PNG is not uploaded during this offline check.
- Geometry tests are conservative and approximate; a clean technical PASS
  still needs independent visual QA and owner approval for release.
- No original children's media, checkpoint weights or private user APIs are
  committed to GitHub.

## Low-cost first bunny art qualification (two parts, not ten)

The operator can run the approved `probe-bunny` command locally on the
Mac **after** the real reference-conditioned ComfyUI workflow/profile
passes `audit-character-workflow`:

```sh
kidsstudio probe-bunny examples/bunny_blueprint.json \
  --workflow /local/private/workflow_api.json \
  --profile /local/private/workflow_profile.json \
  --reference /local/private/bunny_neutral_v01.png \
  --out /local/private/qualifications/bunny_probe_001 \
  --execute
```

This submits **exactly two** model jobs (body + viewer-right arm), sharing
one uploaded canonical reference. Before a third job could be queued, each
image must pass the established real-alpha and anatomical-region validation.

Artifacts retained in a new version folder:
- `parts/body.png`, `parts/arm_right.png`: original transparent source layers
- `probe_contact_sheet.png`: body, arm, and neutral composite over checkerboard
- `probe_report.json`: immutable run provenance, hashes, technical alpha/
  geometry results and measured shoulder-region overlap

Decisions are deliberately conservative:
- `PROBE_FAILED`: missing transparency, bad dimensions, dangerous graph,
  geometry failure, network error or any other attempt failure
- `PROBE_BLOCKED_NO_SHOULDER_OVERLAP`: files may be valid individually,
  but they do not overlap around the arm-right pivot; full generation blocked
- `PROBE_READY_FOR_VISUAL_INSPECTION`: structural prerequisites passed,
  **but neither artistic rig approval nor full-generation authorization**

Check the contact sheet for identity, texture palette, seam color, side of the
body, reference likeness and anatomical plausibility. Even nonzero joint
overlap is *not proof* that waving looks natural: next gate is a live
motion-preview with complete rig parts. No YouTube, paid API, or automatic
publishing path exists in this step.

The CLI runs only when `--execute` is passed on the Mac. The Pi remote
worker cannot dispatch this exploratory probe. It remains owner-controlled
until we see and calibrate real FLUX layers.

## Second gate: independent vision assessment (no ComfyUI regeneration)

The earlier two-part probe now creates **five diagnostic panels**:
BODY, ARM RIGHT, NEUTRAL, ARM +35 DEG and ARM -35 DEG. The last two are
Pillow rotations about the approved shoulder pivot, **not** Godot renders
or a full animation. They expose obvious gaps/ghosting during a basic
arm movement while retaining an inexpensive, partial-rig qualification.

After the local ComfyUI probe reports `PROBE_READY_FOR_VISUAL_INSPECTION`,
run a separate local vision-model review:

```sh
kidsstudio review-bunny-probe \
  --probe-dir /local/private/qualifications/bunny_probe_001 \
  --reference /local/private/bunny_neutral_v01.png \
  --model YOUR_INSTALLED_LOCAL_OLLAMA_VISION_MODEL \
  --execute
```

It checks the source PNG hashes, original identity-reference SHA256,
contact-sheet hash and measured shoulder overlap **before sending images**
to an installed localhost-only multimodal model. There is no repeat
ComfyUI generation, remote API fallback or automatic model download.
The model must explicitly examine style/palette/arm completeness/shoulder
seams and the two simple rotations, not invent defects in absent
head/eyes/legs, which are intentionally not in the probe.

Outputs `probe_visual_review.json` (no overwrite) with typed verdict:

- `PROBE_PRELIMINARY_ART_PASS`: AI sees no specific issues with confidence
  at least 0.90. Still requires human scrutiny and full-rig motion QA.
- `PROBE_ART_REVISION_REQUIRED`: issue(s) seen or confidence insufficient.
  Review instructions and evidence; **no automatic full-rig generation**.
- `PROBE_ART_REJECTED`: serious mismatch or malformed design.
  Avoid wasting more full-character GPU cycles.

Passing **does not** set `full_rig_generation_authorized` or
`public_release_authorized`. Both remain false. Reports are explicitly
tied to input files. Use a new probe directory for a new run.

Note: a local AI visual reviewer can be mistaken. These two art layers
are insufficient to prove 10-part coherent character motion. Quality
is not proven until real ComfyUI art passes multiple full-rig animations.

## Stage zero: inspect the Mac before using the GPU

The first real local step is **read-only**:

```sh
kidsstudio inspect-mac-comfy \
  --workflow /local/private/FLUX_bunny_api.json \
  --report /local/private/mac_diagnostics_v01.json \
  --draft-profile /local/private/UNAPPROVED_profile.json
```

This checks API-format nodes, finds *possible* image-reference,
conditioning, sampler, matting and SaveImage node IDs and saves an
unapproved profile template. The template's checksum is intentionally
**not accepted by the production runner** until the owner checks the
actual workflow and explicitly approves it.

Add `--connect` to query only the user's running local ComfyUI node
registry and basic device statistics, with no POST, model download,
checkpoint read, image upload or inference:

```sh
kidsstudio inspect-mac-comfy \
  --workflow /local/private/FLUX_bunny_api.json \
  --connect --base-url http://127.0.0.1:8188 \
  --report /local/private/mac_diagnostics_v02.json
```

The tool lists missing classes, checks selected model filenames against
node dropdowns if provided, and never writes full private prompts to
the diagnostic JSON. If the file is from File → Save rather than
**File → Export Workflow (API)**, the tool reports the format problem
instead of attempting conversion or sending it to ComfyUI.

For a final no-generation graph check supply all three:
`--profile`, `--blueprint`, `--reference` together; after passing
the approved graph and local node registry, the report says
`READY_FOR_TWO_PART_PROBE_NOT_GENERATED`.

**Important:** graph wiring and node registration cannot establish real
alpha output, identity preservation, licensing, GPU speed or seamless
joint movement. Those only become testable by running the separately
approved 2-part probe on the actual Mac. See [MAC_READINESS.md](MAC_READINESS.md).
