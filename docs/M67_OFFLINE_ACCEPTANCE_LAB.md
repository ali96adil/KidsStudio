# M67.23 — First episode offline acceptance and dry-run

This batch adds an offline handoff lab and a Pi import preflight. Neither
connects to YouTube, invokes ComfyUI/Godot, nor publishes a video.

## 1. Run the offline handoff lab

```sh
python3 -m kidsstudio.m67_offline_handoff_lab
```

The lab creates temporary fixture bytes (not a playable MP4), hashes them,
builds a handoff inventory, verifies consistent plan/readiness references,
and proves that a modified readiness hash is rejected.

## 2. See missing episode evidence on Mac

```sh
python3 -m kidsstudio.m67_readiness_summary \
  --root "$HOME/KidsStudio-Production/colors-ar-001"
```

This is an evidence inventory, not an independent verification of content.
It never reports that a real Pi upload or owner review was performed.

## 3. Dry-run the Pi import

On Pi, use the actual configured paths and M65 render job:

```sh
python3 -m kidsstudio.m67_pi_import_preflight \
  --db /home/studio/kidsstudio/queue.sqlite \
  --inbox-root /home/studio/kidsstudio/inbox \
  --journal /home/studio/kidsstudio/upload_journal.sqlite \
  --render-job-id YOUR_32_CHARACTER_RENDER_JOB_ID \
  --master /home/studio/incoming/EPISODE-HASH.mp4 \
  --plan /home/studio/kidsstudio/receipts/private_upload_plan.json \
  --readiness /home/studio/kidsstudio/receipts/m8_readiness.json \
  --sha256 YOUR_EXACT_MASTER_SHA256
```

It validates deployment structure and receipt consistency without staging
files. A passing dry-run **does not** mean the Pi owner approval and M65
inbox acceptance have been completed.

## 4. Do not bypass the existing uploader

The current Pi private uploader is `kidsstudio.pi_all_private_uploader`.
Its one-shot journal and ambiguous STARTED state handling must remain the
source of truth. Do not introduce a second independent videos.insert client.

## 5. Remaining real-device acceptance

Actual ComfyUI workflow, voice quality, render, Mac/Pi transfer, M65
approved render provenance, Pi intake, one private YouTube upload, and
owner review still require verification. No M67 offline fixture is
proof that these steps happened.
