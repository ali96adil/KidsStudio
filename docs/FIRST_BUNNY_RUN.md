# First real bunny qualification — one owner-controlled command

This is the **first real-art production trial** on the owner's Mac, not a
GitHub-only graphics demonstration. Its goal is to learn whether the
locally installed reference-conditioned FLUX + transparent layering
workflow can output a usable body/arm pair **before** full-rig production.

## 1. One-time Mac setup

This is not an automated installer. Keep the following on your Mac's
private SSD (not in the public GitHub repository):

- Approved ComfyUI API-format workflow JSON with a genuinely connected
  image-conditioning + sampler + alpha/matting path.
- The **approved profile JSON** containing an exact workflow SHA-256,
  permitted node/model classes and selected node IDs.
- Your original canonical bunny PNG and the versioned blueprint.
- An installed locally running ComfyUI at `127.0.0.1:8188`.
- An installed local Ollama multimodal model at `127.0.0.1:11434`.
- Godot/FFmpeg on the Mac, and at least 10 GiB free in the PRIVATE
  output folder. (The Godot preflight is for the future 10-part stage.)

The workstation's previous `mac-doctor` command can inspect these
preconditions without generating artwork.

## 2. Private station config — no tokens

Create `/your/private/path/bunny_station.json`, populated with **your
actual absolute paths**, not guesses:

```json
{
  "schema_version": 1,
  "workflow": "/YOUR/PRIVATE/ComfyUI/bunny_api.json",
  "profile": "/YOUR/PRIVATE/ComfyUI/bunny_approved_profile.json",
  "reference": "/YOUR/PRIVATE/characters/bunny_neutral_v01.png",
  "blueprint": "/YOUR/CLONED/KidsStudio/examples/bunny_blueprint.json",
  "review_model": "YOUR_INSTALLED_OLLAMA_VISION_MODEL",
  "output_root": "/YOUR/PRIVATE/KidsStudio/qualifications",
  "timeout_seconds": 900,
  "min_free_gb": 10
}
```

`output_root` must already exist and be outside any Git worktree.
The private config must also stay outside public Git and can contain
only the documented fields. Store AI API keys separately in the local
system environment; this workflow does not use paid chat APIs.

## 3. ONE command on the Mac

```sh
cd /YOUR/CLONED/KidsStudio
python3 -m pip install -e .
kidsstudio first-bunny-run \
  --config /YOUR/PRIVATE/bunny_station.json \
  --run-name bunny_trial_001 \
  --execute
```

Only the final `--execute` is permitted to start inference. The sequence
is deterministic and fixed:
1. READ-ONLY Mac Doctor: workflow/pinned profile, original PNG, installed
   ComfyUI nodes/models, local Ollama registration, Godot/FFmpeg, disk.
2. If all status checks are ready, upload the canonical reference to
   **local** ComfyUI once, and run **body then arm_right only** (two GPU jobs
   maximum, each one submission; no retries). Each generated PNG must have
   actual alpha and a plausible anatomical region.
3. Verify overlap around the right shoulder, stage two independent PNGs
   and the 5-panel rotation/contact sheet.
4. Only if the shoulder passes, send the sheet + reference to the
   locally installed vision reviewer once. Record its preliminary
   PASS/REVISE/FAIL with SHA256 evidence.

Files under `output_root/bunny_trial_001/` include
`first_run.json` (private, updated after each stage), and,
when created, `probe/parts/body.png`, `probe/parts/arm_right.png`,
`probe/probe_contact_sheet.png`, `probe/probe_report.json`,
`probe/probe_visual_review.json`.

## 4. Exactly-once is deliberately NOT promised

If your Mac loses power mid-GPU call, the versioned attempt folder
remains reserved. KidsStudio **never automatically reuses** the same
run name or sends another model job after an uncertain result. Inspect
the local ComfyUI history and partial output manually; a fresh owner-
authorized attempt must use a new `--run-name`. This avoids accidental
duplicate generation/spending.

Possible outcomes:
- `BLOCKED_AT_PREFLIGHT`: no GPU jobs attempted; fix configuration.
- `BLOCKED_AT_GEOMETRY`: parts were attempted but failed the joint test.
- `STOPPED_UNCERTAIN_NO_AUTORETRY`: source generation/reviewer error;
  inspect the private report/artifacts; no automatic restart.
- `ART_REVISION_REQUIRED` / `ART_REJECTED`: insufficient first art quality.
- `PRELIMINARY_ART_PASS_NEEDS_OWNER`: promising body/arm, but a human
  must **inspect actual composition and motion** before proceeding.

This run explicitly does NOT generate a full rig, publish to YouTube,
approve child-safety or original artistic ownership, or invoke any
paid AI provider.

## 5. What this GitHub CI does/doesn't prove

CI tests the orchestration with mocked Mac Doctor, local ComfyUI and
Ollama interfaces. Older native CI uses synthetic PNG assets with
actual Godot and FFmpeg. **No code in GitHub Actions has run the user's
actual FLUX.2 Klein on their Mac**. The first real test can occur only
once the approved local workflow and source image are available there.
