# M67 — Raspberry Pi first-episode acceptance checklist

This guide extends M65, not replaces it. The existing Pi ordinary uploader
requires a current approved render job, the owner-controlled series/channel
policy, the original upload plan, and M8 readiness evidence.

## Pi dry-run qualification

Run on the Pi from the KidsStudio checkout:

```sh
python3 -m kidsstudio.m67_pi_readonly_audit \
  --db /home/studio/kidsstudio/queue.sqlite \
  --inbox-root /home/studio/kidsstudio/inbox \
  --journal /home/studio/kidsstudio/upload_journal.sqlite \
  --render-job-id YOUR_32_CHARACTER_RENDER_JOB_ID
```

Paths are examples, not detected configuration. Audit does not contact
Google or upload media. If the journal is in STARTED state, **do not
start another videos.insert**; reconcile the existing attempt first.

## Import the Mac MP4 through M65

The raw M67 SSH transfer by itself is not an accepted M65 inbox record.
The original M65 episode approval and render receipt must already exist.
The original M25 private plan and M8 readiness report must correspond to
the same render job and master SHA256. On the Pi:

```sh
python3 -m kidsstudio.m67_pi_ordinary_import \
  --db /home/studio/kidsstudio/queue.sqlite \
  --inbox-root /home/studio/kidsstudio/inbox \
  --render-job-id YOUR_32_CHARACTER_RENDER_JOB_ID \
  --transferred-master /home/studio/incoming/EPISODE-HASH.mp4 \
  --plan /home/studio/kidsstudio/receipts/private_upload_plan.json \
  --readiness /home/studio/kidsstudio/receipts/m8_readiness.json \
  --sha256 YOUR_EXACT_MASTER_SHA256
```

These are placeholders: no M67 tool creates a legitimate M65 approval
from arbitrary JSON. The Pi independently verifies the original approval,
the channel policy, all three staged files, and exact hashes. If this
fails, inspect the staged .part files and database state. Do not retry
blindly.

## Private upload service

Only after M65 accepts the media, use the existing
`kidsstudio.pi_all_private_uploader` service with Pi-only OAuth
credentials. The service uploads **PRIVATE**, and records durable upload
attempts. A STARTED attempt with no persisted video ID is ambiguous:
stop and reconcile rather than creating another video.

The owner reviews the private YouTube video before public release.
Nothing in M67 authorizes a public visibility change.

## Visibility into production

On the Mac, from the repository root:

```sh
python3 -m kidsstudio.m67_episode_status \
  --root "$HOME/KidsStudio-Production/colors-ar-001"
```

The report reads known stage receipts only. It is not a cryptographic
attestation or proof of completed YouTube upload.

## Acceptance still required

- Actual Mac ComfyUI workflow and Iraqi-Arabic voice evaluation.
- A real 75-second MP4 with independent QA evidence.
- Actual Mac-to-Pi SSH transfer and Pi M65 database acceptance.
- A single PRIVATE upload, checked in YouTube Studio.
- Owner feedback on the private video and final release decision.
