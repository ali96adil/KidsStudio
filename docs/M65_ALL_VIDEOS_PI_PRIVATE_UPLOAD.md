# M65 — one Pi uploader for ALL Kids Studio videos

**Owner requirement:** All video generation stays on **Mac**; finished
videos travel across the **local network**, are stored persistently on
**Raspberry Pi**, and are uploaded to YouTube **PRIVATE by Pi only**.
Mac may power down after the LAN copy finishes. Pi verifies processing,
then the existing owner feedback UI records the human final choice.
No Public/upload-scheduling API is installed.

M64 implemented the recovered-montage Pi handoff. M65 extends the same
architecture to **ordinary approved episodes (M25/M26)**, removing the
old split between ordinary-Mac upload and recovery-Pi upload.

## New universal flow

```text
Mac (Godot + local media production, M7 + independent AI checks)
    ├── ordinary approved episode (M8/M25 plan)
    └── M61 recovered episode (M62 independent AI/rights plan)
       |
       | SSH/rsync *.part files over local Wi-Fi/Ethernet
       | macOS optional outbox launchd process (NO YouTube token)
       v
Raspberry Pi persistent upload-inbox (same private root)
    ├── ordinary: FULL SHA, M8/episode_assemble receipt + M26 owner QA
    │             + channel/day-budget policy, private M25 catalogue
    └── recovery: FULL SHA, M55–M63 original lineage/QA/owner policy
       |
       | persistent pi-upload.sqlite STARTED before Google HTTP
       | refreshable Google OAuth grant stored on Pi only
       | M26 or M63 dedicated Pi-local worker/checks and heartbeat
       v
YouTube: one PRIVATE videos.insert with resumable chunks
       |
       | authenticated videos.list checks same channel + PRIVATE state
       | processing=pending: Pi GET-only later, NEVER a new upload
       v
Owner loopback review UI: timestamped notes, accept / accept with
notes / request changes; no automatic Public publishing.
```

**Pi stays on; Mac can be off during hours of Google uploading and
processing.** A restart or an uncertain Google POST/PUT does not launch a
second upload. The durable Pi STARTED journal prevents double posting;
full crash/reboot resumption of an incomplete *Google session* remains
an unqualified future enhancement requiring safe remote offset proof.
LAN rsync transfer itself supports resume with the same .part file.

## Ordinary pipeline added

- `kidsstudio/mac_ordinary_to_pi.py` sends a verified ordinary
  M25 upload plan, final MP4 and M8 readiness report, with Pi-local
  SSH host-key validation and no cloud request on Mac.
- `kidsstudio/mac_outbox_to_pi.py` handles both
  `<proposal-id>.ready.json` recovered plans and
  `<render-job-id>.ordinary.ready.json` ordinary plans. An ordinary
  plan has a corresponding `<render-job-id>.ordinary.m8.json` file
  in the private Mac outbox, while its master is under
  `renders/<render-job-id>/episode_qa_master.mp4`.
- `kidsstudio/pi_ordinary_inbox.py` independently validates media
  bytes and M8 JSON against current original Pi completed render
  receipt, M7/AI technical approvals, approved episode and owner
  channel. It creates one immutable Pi M25 private catalogue.
- `kidsstudio/pi_ordinary_uploader.py` invokes the original M26
  enqueue/lease/policy gate against **Pi-local** approved files. Its
  targeted claim cannot accidentally claim another episode's queued
  upload. It runs the M25 Google HTTPS transport on Pi with refreshed
  Pi-only OAuth tokens, never a Mac token.
- `PrivateUploadPolicy.reconcile_pi_processing` checks the **same
  completed M26 job and same existing YouTube ID**, still-current
  owner policy, exact master SHA and approved episode before opening
  a M24 private-owner review after Pi GET-only verification. This
  cannot create or repeat a videos.insert call.
- `kidsstudio/pi_all_private_uploader.py` is the single service
  running both recovery and ordinary Pi branches. The supplied
  systemd template now launches this combined service.
- The legacy Mac M63 recovery executable and M26 ordinary Mac
  `--execute` CLI are both **explicitly disabled** for YouTube; no
  dual upload locations. The old classes remain tested and reused
  by the Pi-local process.

## Local operational setup

These are **reference steps**, not commands executed on owner devices
in this branch. Do not start production until tests and owner Pi/Mac
network, disk, OAuth and private-channel verification are qualified.

### Pi

Persistent SSD recommended for large videos. Provision user
`kidsstudio` (not root), local SSH transfer permissions only to
`/var/lib/kidsstudio/upload-inbox`, and Pi owner database outside Git.

```sh
# M25/26 and M62/63 schema/policies must already exist as relevant.
python -m kidsstudio.pi_all_private_uploader \
  --db /var/lib/kidsstudio/studio.sqlite \
  --inbox-root /var/lib/kidsstudio/upload-inbox \
  --journal /var/lib/kidsstudio/pi-upload.sqlite --initialize

# This is a dry-run; does not use Google.
python -m kidsstudio.pi_all_private_uploader \
  --db /var/lib/kidsstudio/studio.sqlite \
  --inbox-root /var/lib/kidsstudio/upload-inbox \
  --journal /var/lib/kidsstudio/pi-upload.sqlite
```

Store **only on Pi**, in root-owned 0600 systemd EnvironmentFile
`/etc/kidsstudio/pi-youtube-oauth.env`, the channel-authorized OAuth
client ID, client secret, and refresh token under
`KIDSSTUDIO_PI_YT_CLIENT_ID`,
`KIDSSTUDIO_PI_YT_CLIENT_SECRET`, and
`KIDSSTUDIO_PI_YT_REFRESH_TOKEN`. Never put them in Git, Mac outbox
or this chat. Use edited
`deploy/kidsstudio-pi-private-uploader.service` which now starts
`kidsstudio.pi_all_private_uploader` with `--execute --loop`.
Enable it only after a supervised PRIVATE-only channel test.

### Mac

Local render and complete QA first. A private `.ready.json` plan
signals that the AI/rights workflow has staged an approved candidate;
the Pi still checks original current episode policy and refuses any
stale/forged source.

```sh
# Dry-run: no SSH and no Google.
python -m kidsstudio.mac_outbox_to_pi \
  --outbox /PRIVATE/mac/outbox --renders /PRIVATE/mac/renders \
  --pi-host pi-kids.local --pi-user kidsstudio \
  --pi-inbox-root /var/lib/kidsstudio/upload-inbox \
  --ssh-key /PRIVATE/mac/.ssh/kidsstudio_transfer

# Qualified use: add --execute --loop or edit the launchd template.
```

The Mac sender writes `.sent` after rsync completes. The Pi never
trusts that as final approval; it re-hashes all received bytes and
re-checks policy before Google. If transfer is interrupted, rsync
resumes the same .part files; if the Pi rejects QA, it does not upload.

## Testing / limitations

Tests combine real SQLite approval/scene receipts, fake YouTube
PRIVATE-only responses, exact local file bytes and simulated rsync.
They exercise both ordinary and recovery Pi paths, source mutation,
M8/AI/owner policy mismatch, one-shot upload, Pi-only OAuth refresh,
YouTube processing-pending and GET-only completion. Synthetic tests
are **not** real Pi/Mac network or real Google upload qualification.
The production OAuth grant still needs to be set up securely on Pi.

**No generated media and no Google credentials have been uploaded
during development.** Draft PR #28 remains unmerged until hardware,
local storage, SSL/SSH and actual PRIVATE test-upload qualification.
