# Mac ComfyUI preflight and owner workflow provisioning

This milestone intentionally removes the guesswork from connecting an
already installed Mac ComfyUI instance to KidsStudio. **It is a passive
diagnostic and cannot generate any art or execute arbitrary remote code.**

## 1. Export the right file

In the owner's local ComfyUI frontend, open the intended FLUX.2 Klein
workflow and select **File → Export Workflow (API)**. This creates
the node-ID-indexed JSON used by `/prompt`; the ordinary visual editor
JSON (`nodes[]`, `links[]`) is not a runnable API graph.

Run `kidsstudio inspect-mac-comfy` with that exported API JSON. It
reads only the chosen file and checks:
- Missing or suspicious externally executing node classes, incorrectly
  formatted graphs and 160-node cap
- Standard prompt/reference/save node candidates; plausible (NOT
  guaranteed) identity conditioner/sampler/matting node candidates
- SHA-256 of workflow source; unknown model files from the workflow
  are **not** auto-downloaded
- Private owner approval is always required before any production run

## 2. Read the installed ComfyUI capabilities (explicit opt-in)

Use `--connect`. This enables only **HTTP GET** to loopback
`http://127.0.0.1:8188/object_info` and `/system_stats`.
Local-only, no HTTP proxy, no redirects, bounded response sizes.
`/object_info` declares each registered node and available input
choices. If a model loader exposes a fixed model choice list, the
diagnostic checks whether the workflow's chosen checkpoint is there.
If the loader uses dynamic values, its availability remains unverified.
The diagnostics intentionally record **device count**, not private
device names or full raw node schemas.

Results may include:
- `EDITOR_FORMAT_NOT_API`: re-export with *Export Workflow (API)*
- `MISSING_LOAD_IMAGE` / `MISSING_SAVE_IMAGE`:
  source workflow lacks standard supported nodes
- `WORKFLOW_HAS_MISSING_NODES`: install/review missing custom nodes
  locally after checking provenance and code; no automatic install
- `SELECTED_MODEL_NOT_AVAILABLE`: chosen checkpoint not listed by
  installed loader; inspect its exact supported filename
- `LOCAL_COMFYUI_UNAVAILABLE`: local server offline/wrong port
- `APPROVED_GRAPH_AUDIT_FAILED`: checksum, wiring or approved profile
  not valid; verify graph and node IDs

No user image, model weight, credentials, provider tokens, private
prompts or ComfyUI history are sent to GitHub by this tool.
A local diagnostic report still deserves private storage.

## 3. Proposed profile is NOT authorization

`--draft-profile /private/UNAPPROVED_profile.json` writes an intentionally
unapproved template and never replaces an existing file. It provides
candidate node IDs and model names for manual inspection, but contains
`OWNER_MUST_APPROVE_<sha256>` instead of a usable workflow approval.
The owner must inspect the node semantics and ensure the canonical
image really conditions the sampler, and a true alpha/matte node feeds
the selected SaveImage. Then populate the actual private profile,
remove the draft's `_note`, and approve exact workflow hash explicitly.

With `--blueprint`, `--profile`, `--reference` *together*,
the inspector runs the existing checksum-pinned graph audit (read-only).
`READY_FOR_TWO_PART_PROBE_NOT_GENERATED` is reported only if this
audit passes and the explicitly connected local ComfyUI has all
required node classes, with no selected model known to be missing.
Even then the status means **no generation occurred**.

## 4. Next real production gate

Only after this preflight may the user explicitly run
`kidsstudio probe-bunny ... --execute` on the Mac to generate body
and right arm. This remains a **manual** 2-GPU-job test, followed by
geometry inspection and optionally local-vision review; no automated
full rig, paid AI or YouTube publishing.

### Current status

Implemented and fake-local-server tested in GitHub CI.
The actual owner's Mac, FLUX.2 Klein checkpoint filename,
installed ComfyUI custom nodes and approved reference/alpha workflow
have **not** been inspected by this chat. No private models or artwork
were committed.
