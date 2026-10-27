# Local ComfyUI adapter — M1

The first adapter is intentionally narrow. It uses local ComfyUI's API at
http://127.0.0.1:8188 and refuses nonlocal hosts, unapproved model names,
external provider classes and unapproved workflow checksum changes.

## Getting a reusable workflow

1. Keep your ComfyUI Desktop instance local.
2. Open the **known-good text-to-image workflow** on the Mac.
3. Export the workflow in **API format** (not the ordinary UI graph format).
4. Determine the standard CLIPTextEncode node id and SaveImage node id from
   the exported object. For alternate custom nodes, do not override security
   checks: extend/verify an explicit adapter instead.
5. Record the exact SHA-256 of the API JSON (shasum -a 256 FILE).
6. Create a **local** profile JSON containing the approved node class types,
   all approved model filenames, prompt node id and SaveImage node id.

The previous FLUX.2 image edit with FP8 failed on Apple MPS. Use only a
known-good non-FP8 checkpoint for initial testing. Never auto-pull a model.

### Example profile (illustrative, NOT pre-approved)
    {
      "approved_workflow_sha256": "REPLACE_WITH_REAL_SHA256",
      "allowed_node_classes": ["CLIPTextEncode", "UNETLoader", "SaveImage"],
      "approved_model_names": ["flux-2-klein-base-4b.safetensors"],
      "prompt_node_id": "1",
      "filename_node_id": "9"
    }

The profile's allowlists are mandatory; the workflow must itself be
scrutinized before its hash is approved. Don't put API keys or child data
in the workflow.

## Modes

Dry run (does not send a network request or generate any image):

    kidsstudio comfy-prepare /path/to/workflow_api.json \
      --profile /path/to/profile.json \
      --prompt "Original bunny neutral pose, isolated..." \
      --prefix KidsStudio/test/bunny

Explicit queue operation, only once the dry run succeeds:

    kidsstudio comfy-prepare /path/to/workflow_api.json \
      --profile /path/to/profile.json \
      --prompt "Original bunny neutral pose, isolated..." \
      --prefix KidsStudio/test/bunny --submit

The original `comfy-prepare` command is a narrow graph-preparation tool.
`build-character` now handles local reference uploads, bounded sequential
part collection and visual-review staging. For production readiness, use
the stronger offline audit in [WORKFLOW_READINESS.md](WORKFLOW_READINESS.md).
This does not mean live Mac artistic output has been verified.

## Identity-conditioned rig parts (new)

For character continuity, **use a vetted reference-conditioned API workflow**.
Its profile must set `reference_node_id` to the id of an approved standard
`LoadImage` node that **actually feeds the SaveImage output graph**.
Disconnected cosmetic reference nodes are rejected.

The workflow must additionally have model-specific image-conditioning nodes
that produce visually consistent isolated parts. Merely connecting LoadImage
somewhere in the graph is a minimum wiring check, **not** proof the model used
the reference effectively. Use the canonical reference + local visual review
to catch mismatches.

`build-character --reference /path/to/canonical_bunny.png` validates the
PNG, computes a hash-based safe filename, uploads it only to the loopback
ComfyUI input endpoint, and uses its filename in all per-part jobs.
The original file stays on the Mac, outside Git. The factory report records
its SHA256, not the image itself.

If the profile demands a reference and none is given, preparation **fails**.
Never quietly revert to text-only generation for an approved character.

## Production readiness and exact output provenance

See [WORKFLOW_READINESS.md](WORKFLOW_READINESS.md). A connected reference node alone no longer qualifies as a production rig workflow. `production_contract` must prove the image-conditioning branch feeds the approved sampler, with text and image input, followed by an alpha/matting stage before the selected SaveImage. The part collector uses the exact output node ID in ComfyUI history and rejects multiple/missing images.
