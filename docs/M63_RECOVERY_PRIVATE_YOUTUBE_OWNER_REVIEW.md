# M63 — Recovery-only YouTube PRIVATE upload + owner review

**Status:** DRAFT PR #28; no code merged to `main`. Real owner Mac,
Pi, Google OAuth and production channel were **not** operated. Successful
synthetic tests are NOT evidence that a real upload has occurred.

## Architecture and security boundary

M61 creates an independent recovered montage master with its own SHA-256
and job ID, leaving the original failed queue job and BLOCKED episode
untouched. M62 pins fresh full M7 technical QA, two independently
identified educational and child-safety AI reports, external asset rights,
and the standing M26 policy for an exact channel and audience setting.
M63 **never forges the original ordinary M25/M26 job** and keeps their
source checks unchanged.

### Pi private uploader

`kidsstudio/recovery_private_upload_gate.py` introduces additive
`studio_recovery_uploads`, `studio_recovery_owner_feedback` and
`studio_recovery_owner_decisions` tables. The local Pi operator
initializes and explicitly activates a staged M62 handoff. It checks
current M57–M62 source provenance, unchanged final master SHA,
the original FAILED/CANCELLED job and BLOCKED episode, two-agent AI
readiness, and an ENABLED M26 standing policy with the same channel,
audience/synthetic disclosure and policy revision. The same **per-series
24h owner upload limit** counts ordinary YouTube jobs and recovery
attempts together, and another active ordinary or recovery upload
prevents activation.

A separately provisioned TLS worker with capability
`recovery_private_upload` can claim exactly one proposal. It cannot
claim regular queue jobs or the M61 rendering capability. Endpoints:

- `recovery-private-claim` — one targeted proposal/job identity
- `recovery-private-check` — pre-network lease, source and policy checks
- `recovery-private-heartbeat` — renew lease after current policy check
- `recovery-private-complete` — only exact SHA/channel, YouTube PRIVATE
  status, one video ID and explicit processing/owner review state
- `recovery-private-fail` — terminal reconciliation; no auto retry
- `recovery-private-reverify` — **same authenticated worker and already
  uploaded YouTube video ID only**, no second insert

Expired or revoked upload permission never restarts automatically.
The original M26 uploaded-video gates remain unchanged.

### Mac upload agent

`kidsstudio/recovery_private_uploader.py` accepts an explicit
owner-reviewed local JSON upload plan: exact M61 recovery job ID, exact
M62 handoff series/channel/audience settings, full local MP4 SHA,
title/description and category.

Its CLI is **no network by default**. With `--execute` and a separately
configured recovery upload worker token (Mac environment variable
`KIDSSTUDIO_WORKER_TOKEN`) and Google OAuth bearer
(`KIDSSTUDIO_YOUTUBE_ACCESS_TOKEN`), it:

1. Validates the exact original M61 master file SHA and owner metadata.
2. Claims an isolated M63 Pi lease and validates its series, proposal,
   video SHA, channel and audience flags.
3. Creates exactly one durable `UploadJournal.STARTED` record **before**
   any Google videos.insert call; rejects duplicate/uncertain attempts.
4. Rechecks the Pi policy and local media SHA **after** journal STARTED,
   immediately before the FIRST Google upload HTTP call; renews Pi lease
   while working. Any policy change, failed heartbeat or Mac file
   mutation fails closed without a second request.
5. Uses the hardened existing `GoogleYouTubeTransport` resumable
   HTTPS uploader. Metadata explicitly sets
   `privacyStatus=private`, makes the exact made-for-kids and
   synthetic-media declarations, and suppresses subscriber alerts.
   No call can set PUBLIC or schedule publication.
6. Verifies the existing new YouTube video ID through authenticated API:
   exact channel ID, `privacyStatus=private`, processing state.
   Only `processingStatus=succeeded` qualifies for owner review.
7. Sends a bounded metadata receipt to the Pi, which pins the video ID
   to the recovery proposal/master. The Pi trusts the authenticated Mac
   worker's Google API receipt; the Pi does **not** independently call
   YouTube. A SHA or remote-reported status alone is not a legal or
   educational review.

If the first upload is accepted but YouTube is still processing, M63
stores `M63_YOUTUBE_PRIVATE_PROCESSING_PENDING` with the same video ID.
A later explicit `--verify-existing --execute` performs a **GET-only**
Google check and can promote that SAME video to owner review, with no
new upload. Unknown network outcomes always require reconciliation;
they are never re-uploaded automatically.

### Owner review (same local UI)

`kidsstudio/recovery_owner_review.py` stores independent feedback
using the same M24 categories and controls:

- free-text feedback with optional 00:42-style scene timestamp
- APPROVE, APPROVE_WITH_NOTES and REQUEST_CHANGES decisions
- one final decision per exact private recovered video
- revision/accepted-with-notes handoff to agent planning, not a blind
  automatic re-render or new upload

`owner_review_ui.py` adds verified recovered private previews to the
same token-authenticated loopback UI and routes comments/decisions to the
recovery ledger only when the video ID belongs there. Existing ordinary
M24 video IDs cannot overlap recovery video IDs. Owner approval
**NEVER** invokes YouTube public/scheduled visibility APIs.

The Pi dashboard now separately reports READY / LEASED / PROCESSING /
PRIVATE_VERIFIED_OWNER_REVIEW_PENDING / approved / revisions. Current
YouTube visibility is not guaranteed in the dashboard after the past
API check; a fresh API read would be necessary for a current claim.

## Reference-only commands (not device qualification)

On Pi (after M62 final QA and policy handoff):
```sh
python -m kidsstudio.recovery_private_upload_gate \
  --db /PRIVATE/pi/studio.sqlite --initialize

python -m kidsstudio.recovery_private_upload_gate \
  --db /PRIVATE/pi/studio.sqlite --activate \
  --proposal-id M56_32_HEX_PROPOSAL
```

On Mac, with an approved `recovery_private_upload` TLS credential and
a **separate** owner channel OAuth bearer in environment:
```sh
# Dry-run; this makes NO HTTP request.
python -m kidsstudio.recovery_private_uploader \
  --pi-url https://PRIVATE_PI_HOST:PORT \
  --worker-id mac-recovery-private \
  --ca-file /PRIVATE/mac/pi-ca.crt \
  --plan /PRIVATE/mac/recovery_private_upload_plan.json \
  --media /PRIVATE/mac/renders/RECOVERY_JOB/episode_qa_master.mp4 \
  --journal /PRIVATE/mac/upload_journal.sqlite

# ONLY after real supervised device qualification, add --execute
# to perform the ONE owner-policy-authorized PRIVATE upload.

# After processing-pending, with SAME plan/media/journal and tokens:
# add --verify-existing --execute to make GET-only follow-up.
```

Example Mac-local **plan format**:
```json
{
  "schema_version": 1,
  "series_id": "colors-ar",
  "episode_number": 1,
  "proposal_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "recovery_job_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "master_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
  "target_channel_id": "UCaaaaaaaaaaaaaaaaaaaaaa",
  "title": "Original Colours Lesson",
  "description": "Educational video with two colors",
  "category_id": "27",
  "made_for_kids": true,
  "contains_synthetic_media": true
}
```
Example placeholders are NOT real owner values and must be replaced with
a current verified M61/M62 handoff. No sensitive credentials, OAuth
tokens, or media file bytes are transferred to Pi or stored in Git.

## Test qualification and known limits

Synthetic tests cover two-scene Pi/source lineage, original queue
isolation, owner policy revocation, exact private channel/master,
no retry, pending processing, cross-ledger identity, saved timestamp
comments and owner decisions; fake HTTPS/Google upload checks exact
`private` metadata, single videos.insert, and no second POST.

**Not yet proven in owner environment:** OAuth token expiration during
upload, genuine Google resumable upload/processing, production Mac/Pi
TLS and heartbeat timing, actual audiovisual/AI judgments, independent
asset-rights legal proof, owner's final video review and Public release.
Keep PR #28 DRAFT until owner Mac/Pi qualification and a confirmed
PRIVATE test upload. No software component makes media PUBLIC by default.
