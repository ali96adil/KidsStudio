# M67 — Mac local production runbook

The episode's media files are **never committed to Git**. These commands
operate on a private directory outside the KidsStudio checkout. They do not
upload to Raspberry Pi or YouTube.

## 1. Prerequisites

On the Mac, confirm `godot --version`, `ffmpeg -version`,
`say -v '?'` and local ComfyUI availability. Choose an **actual installed
Arabic voice** from `say -v '?'`; macOS voice quality and Iraqi pronunciation
require listening review. In ComfyUI, export a working workflow in **API
format** containing a `CLIPTextEncode` node and a `SaveImage` node.
Use the intended model and reference-image conditioning in that workflow;
the Python batch tool only replaces the prompt text of the selected node.
A bare workflow or a node ID copied from another installation will not work.

## 2. Prepare episode outside Git

From the repository root:

```sh
python3 -m kidsstudio.m67_produce prepare \
  --storyboard examples/m67_colors_red_episode_001.json \
  --root "$HOME/KidsStudio-Production/colors-ar-001"
```

This writes `jobs.json`, `manifest.json`, `storyboard.json`, and the
`art/` and `voice/` directories. The destination must not already exist.

## 3. Generate images and voice

```sh
python3 -m kidsstudio.m67_produce generate \
  --root "$HOME/KidsStudio-Production/colors-ar-001" \
  --workflow "$HOME/comfy-workflow-api.json" \
  --text-node 6 --voice "YOUR_INSTALLED_ARABIC_VOICE"
```

Replace `6` with the **actual** CLIPTextEncode node ID. This command runs
six ComfyUI jobs followed by six macOS `say` jobs. It is deliberately
non-resumable: if a batch fails, inspect its report and use a fresh episode
root rather than overwriting a partial run. AI output remains unapproved.

**Important limitations:** current voice output is basic macOS TTS, not a
verified Iraqi dialect model; image generation is conditioned only by the
workflow you provide, and its consistency must be reviewed. ComfyUI must
return exactly one 1280×720 PNG per beat.

## 4. Inspect the generated files

```sh
python3 -m kidsstudio.m67_produce inspect \
  --root "$HOME/KidsStudio-Production/colors-ar-001"
```

This produces `media_inspection.json` with hashes, WAV durations and
structural validation results. **Structural validation is not visual,
educational, copyright or audio-quality approval.**

## 5. Independent QA and manifest pinning

A separate reviewer or QA agent must inspect the actual six images and
recordings. An approvals JSON must contain the matching episode ID and six
entries, each with:

```json
{
  "beat": 1,
  "art_sha256": "<exact sha256 from media_inspection.json>",
  "voice_sha256": "<exact sha256 from media_inspection.json>",
  "visual_qa": "PASS",
  "voice_qa": "PASS"
}
```

Wrap those entries in `{"episode_id":"colors-ar-001","assets":[...]}`.
Only use PASS after reviewing the actual files, **not** merely because the
technical inspector succeeded. Then:

```sh
python3 -m kidsstudio.m67_produce pin-reviewed \
  --root "$HOME/KidsStudio-Production/colors-ar-001" \
  --approvals "$HOME/episode-qa-approvals.json"
```

This creates `reviewed_manifest.json`, preserving the original manifest.
Next stages require the reviewed rig, Godot render, independent animation QA
and final master QA before a private transfer to the Pi can be authorized.
Public publication remains owner-controlled.

## Known gaps before end-to-end hardware acceptance

- ComfyUI API workflow and character reference are not yet packaged for
  the specific local ComfyUI installation.
- macOS voice selection and Iraqi-Arabic pronunciation have not been
  qualified on the user's Mac.
- End-to-end Mac render, LAN transfer and Pi private upload have **not**
  been exercised by these tests.
- QA PASS records are assertions by a reviewer; this tool checks exact
  hashes but does not establish reviewer identity or independently
  evaluate educational quality.
