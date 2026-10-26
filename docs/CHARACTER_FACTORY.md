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

**Technical success = NEEDS_INDEPENDENT_VISUAL_REVIEW.**
It is not an artistic PASS. There is no automatic artistic agent approval yet.
Visual reviewer must examine the actual seams, limbs, face and motion. This
prevents the old shoulder-cut artefact from being silently accepted.

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
