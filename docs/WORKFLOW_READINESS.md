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
