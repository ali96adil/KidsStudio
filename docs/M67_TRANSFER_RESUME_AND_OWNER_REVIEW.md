# M67.25 — Safe Mac-to-Pi transfer and private review

## Transfer: retry without duplicate copying

The M67 transfer-resume command checks for a completed file with the
expected SHA256 before copying again:

```sh
python3 -m kidsstudio.m67_pi_transfer_resume \
  --root "$HOME/KidsStudio-Production/colors-ar-001" \
  --inventory "$HOME/KidsStudio-Production/colors-ar-001/master_inventory.json" \
  --host pi.local --user studio --remote-dir /home/studio/incoming
```

The SSH host must already be trusted and key authentication configured.
The remote directory must already exist. A verified existing MP4 is
reused; an existing partial file causes a hard stop for reconciliation.
The tool does not continue a partial SCP stream from an offset.

## Owner review of a private upload

Once the *existing M65 private uploader* has returned a real YouTube
video ID, the owner can keep append-only notes:

```sh
python3 -m kidsstudio.m67_owner_review_notes \
  --root "$HOME/KidsStudio-Production/colors-ar-001" \
  --episode-id colors-ar-001 --video-id YOUR_VIDEO_ID \
  --decision REQUEST_CHANGES \
  --notes "Pronunciation of red needs another take"
```

Supported review decisions: ACCEPT_PRIVATE, ACCEPT_WITH_NOTES,
REQUEST_CHANGES, REJECT. This only records feedback. It does not
alter the video, trigger an upload, or change YouTube visibility.

## Safety boundary

Do not treat successful SSH transfer, local hashes, or owner notes as
permission to publish. The existing M65 policy and upload journal remain
authoritative for private uploads. Public release requires a separate,
explicit owner action.

## Testing

The transfer-resume unit tests use a simulated SSH runner and check:
a verified existing file is not copied again; an ambiguous partial
blocks; a first transfer verifies both hashes. Real Pi networking,
interrupted power, YouTube upload, and owner UI are not covered.
