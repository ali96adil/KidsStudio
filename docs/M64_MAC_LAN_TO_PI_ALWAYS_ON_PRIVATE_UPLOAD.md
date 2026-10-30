# M64 — Mac renders locally; Pi stores/uploads YouTube PRIVATE

**Changed architecture (owner correction).** The Pi is the always-on
YouTube uploader, **not the Mac**. Mac creates the full local video,
audio and montage, performs current M7 and independent AI/rights checks,
then sends the exact approved MP4 and owner channel plan over the LAN
to Pi. Pi persists the media, hashes it independently and uploads
YouTube PRIVATE using **Pi-only OAuth**. Mac can be powered off once
the LAN transfer has completed. No Google token is stored or used on
Mac by the new M64 path.

**Current scope:** This release applies to the M55–M63 **recovered
montage** path. The older M26 ordinary episode uploader still has a
Mac implementation in the repository; ordinary episodes need the
equivalent Pi-side handoff before declaring the entire studio migrated.
The M63 Mac recovery uploader executable has been disabled. Do not
treat recovery-only M64 as proof that all earlier upload agents migrated.

## Data flow

```text
Mac/Godot/ComfyUI/LTX/Chatterbox -> M61 recovery master + M62 AI/rights QA
    |
    | private .ready.json plan in Mac outbox
    | Mac launchd: kidsstudio.mac_outbox_to_pi --loop --execute
    | SSH (known-host pin, dedicated key), rsync --partial --inplace
    | NO Google OAuth and NO Google HTTP on Mac
    v
LAN, Raspberry Pi: /var/lib/kidsstudio/upload-inbox/<recovery-job-id>/
    episode_qa_master.mp4.part
    private_upload_plan.json.part
    |
    | Pi side: M62 owner policy and episode/scene validation
    | FULL local SHA256, fsync and exclusive acceptance
    v
Pi private persistent media store
    episode_qa_master.mp4
    private_upload_plan.json
    |
    | M63 one-shot local Pi lease and pi-upload.sqlite journal
    | Pi OAuth refresh/token stored only on Pi (secrets not in Git)
    | Google HTTPS resumable transfer, always privacyStatus=private
    v
YouTube PRIVATE video, authenticated processing/channel verification
    |
    | Pi owner review UI, timestamp comments, approve / revisions
    v
ONLY owner decision. PUBLIC changes are a separate, unimplemented action.
```

## What persists when Mac is offline

- The Pi holds its **own real MP4 bytes**, private plan JSON, complete
  SHA256 metadata and Google upload journal under persistent storage.
- Once the Pi has accepted the LAN copy, Mac is no longer involved in
  the Google upload or processing-status verification.
- A long Google upload runs inside the Pi's systemd service with
  heartbeat and strict current owner policy/episode checks.
- OAuth access tokens can be refreshed by the **Pi**, without a Mac
  session, using a Google OAuth refresh grant stored in the Pi
  environment (client ID, client secret, refresh token).
- If YouTube reports processing pending, Pi's next cycle performs
  **GET-only** verification on the same video ID; it never starts a
  second videos.insert.
- If transfer over LAN is interrupted, Mac retries/resumes the same
  *.part files via rsync, **before** Pi accepts; no duplicate episode.
- If an upload has an uncertain network result, the Pi *fails closed*
  with an on-disk STARTED journal and manual reconciliation instead
  of silently uploading a second copy. **Crash-proof automatic resume
  of the Google resumable session is NOT yet qualified.** This is
  separate from the completed LAN transfer's recoverability.

## New modules

- `kidsstudio/mac_to_pi_transfer.py` — Mac direct SSH/rsync LAN copy
  of frozen recovered master and exact plan. SSH key must be 0600,
  host name/username/root are allowlisted; existing remote per-job
  target directory is prepared by Pi.
- `kidsstudio/mac_outbox_to_pi.py` — optional Mac launchd watcher
  reads private `*.ready.json` plans and sends automatically, writes
  an exclusive `.sent` marker only after rsync completed. Pi remains
  sole authority to accept SHA and approve upload.
- `kidsstudio/pi_media_inbox.py` — Pi creates private staging,
  validates M62 owner/source plan, independently hashes the entire
  MP4, atomically promotes to readonly storage, writes one immutable
  `studio_recovery_pi_media` receipt. A transferred SHA alone is not
  a verified Pi receipt.
- `kidsstudio/pi_recovery_uploader.py` — Pi-local private policy
  adapter, long-running server loop, private journal, separate
  OAuth refresh-token provider and GET-only processing recheck.
  Uses existing Google PRIVATE-only upload transport; no arbitrary
  shell or remote upload activation.
- `deploy/kidsstudio-pi-private-uploader.service` — disabled
  example systemd service for Pi (runs under dedicated kidsstudio
  account, persistent journal, no public operation).
- `deploy/kidsstudio-mac-to-pi.launchd.plist.example` — optional
  Mac background LAN sender. **Replace all placeholders before use.**

## Deployment outline — reference, NOT yet for production devices

**Prerequisites on Pi:**
- Persistent disk with sufficient space for master MP4, Pi database
  and YouTube journal; do not fill Pi system SD card. Prefer a
  reliable SSD when uploading multi-GB videos.
- Pi reachable from Mac over local LAN using SSH and a **dedicated,
  narrowly-scoped transfer account** with a pinned SSH host key.
  Run receiving and uploader as the same appropriately restricted
  service account; only that account may access the inbox.
- Pi system time/clock, DNS and HTTPS to Google must be correct.
- Existing M62/M63 Pi database schemas, approved series policy and
  handoff, and M64 inbox schema initialized.

```sh
python -m kidsstudio.pi_media_inbox \
  --db /var/lib/kidsstudio/studio.sqlite \
  --root /var/lib/kidsstudio/upload-inbox --initialize

python -m kidsstudio.recovery_private_upload_gate \
  --db /var/lib/kidsstudio/studio.sqlite --initialize

# Dry-run: no OAuth or Google network call
python -m kidsstudio.pi_recovery_uploader \
  --db /var/lib/kidsstudio/studio.sqlite \
  --inbox-root /var/lib/kidsstudio/upload-inbox \
  --journal /var/lib/kidsstudio/pi-upload.sqlite
```

For Mac, a prepared and approved per-episode plan exists as
`/PRIVATE/mac/outbox/<proposal-id>.ready.json`, and its source media
is at `/PRIVATE/mac/renders/<recovery-job-id>/episode_qa_master.mp4`.
The Pi service prepares `/var/lib/kidsstudio/upload-inbox/<job-id>`
while polling the M62 approved handoffs.

```sh
# Dry-run on Mac: no SSH / no upload.
python -m kidsstudio.mac_outbox_to_pi \
  --outbox /PRIVATE/mac/outbox --renders /PRIVATE/mac/renders \
  --pi-host pi-kids.local --pi-user kidsstudio \
  --pi-inbox-root /var/lib/kidsstudio/upload-inbox \
  --ssh-key /PRIVATE/mac/.ssh/kidsstudio_transfer

# ONLY after local qualification, add --execute --loop,
# or install the edited launchd template.
```

On Pi, only after private channel ownership and OAuth credentials are
configured, install the example systemd unit. The root-owned
`/etc/kidsstudio/pi-youtube-oauth.env` must use mode **0600** and contain
only the intended Pi service's values:

```text
KIDSSTUDIO_PI_YT_CLIENT_ID=<Google OAuth client ID>
KIDSSTUDIO_PI_YT_CLIENT_SECRET=<Google OAuth client secret>
KIDSSTUDIO_PI_YT_REFRESH_TOKEN=<Google OAuth refresh token scoped to upload>
```

These are **placeholders**, never put real secrets in Git or in video
metadata. Owner must first complete a supported OAuth consent flow
to obtain an upload-capable refresh token for the correct channel.
Do not request credentials in this chat. The example service starts
with `--execute --loop` and should not be enabled until independent
hardware and real PRIVATE-only tests pass.

## CI and device qualification

Synthetic tests exercise complete Mac-to-Pi *.part transfer behavior,
independent Pi SHA+fsync acceptance and modification rejection,
one-shot Pi upload using a fake Google client, final private ownership
verification and GET-only pending-processing. They also check Mac
outbox idempotence and fake OAuth refresh caching. No real Google
YouTube upload, no physical Mac-to-Pi network, and no real OAuth keys
were used. Real end-to-end qualification remains before enabling
launchd/systemd or merging PR #28.

**Owner review** remains after upload as PRIVATE. The existing owner
UI records timed feedback, accept-with-notes or request revisions;
nothing makes the video Public by default.
