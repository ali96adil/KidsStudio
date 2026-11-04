# M67 — Mac to Raspberry Pi delivery

The Mac renders locally. The Pi is responsible for long-running YouTube
uploads. The Mac-to-Pi transport uses SSH/SCP with host-key verification and
key-based noninteractive authentication.

## Raspberry Pi preparation (once)

Create a private incoming directory on the Pi, owned by the SSH user,
for example `/home/studio/incoming`. Configure SSH key access from the Mac.
Check the Pi host key independently before connecting. Do not copy YouTube
OAuth credentials to the Mac. Do not expose the Pi SSH service publicly.

## Mac master inventory

After local render and final video QA, from the KidsStudio checkout:

```sh
python3 -m kidsstudio.m67_master_handoff \
  --root "$HOME/KidsStudio-Production/colors-ar-001" \
  --master "$HOME/KidsStudio-Production/colors-ar-001/render/colors-ar-001_preview.mp4" \
  --episode-id colors-ar-001 \
  --output "$HOME/KidsStudio-Production/colors-ar-001/master_inventory.json"
```

This is only an integrity inventory, not QA or transfer authorization.

## Transfer to Pi

```sh
python3 -m kidsstudio.m67_pi_ssh_transfer \
  --root "$HOME/KidsStudio-Production/colors-ar-001" \
  --inventory "$HOME/KidsStudio-Production/colors-ar-001/master_inventory.json" \
  --host raspberrypi.local --user studio \
  --remote-dir /home/studio/incoming \
  --output "$HOME/KidsStudio-Production/colors-ar-001/pi_transfer_report.json"
```

Replace the hostname, user and directory with the actual Pi setup.
The destination must exist. The transfer refuses to overwrite a previous
master. It verifies SHA256 on the Pi before and after moving the temporary
file to its final name. If interrupted, a `.partial` file can remain on
the Pi; inspect and clean it manually before retrying.

The resulting MP4 stays on the Pi independently of the Mac's power state.
This transport does **not** upload to YouTube, request publication or
authorize a public release. A separate Pi uploader must use the Pi's own
credentials and upload PRIVATE. The owner then reviews and approves any
future change to public visibility.

## Qualification boundary

The transfer path has unit tests with a mocked SSH runner. It has **not**
yet been executed against the actual Mac and Raspberry Pi. Confirm network,
disk space, permissions and real end-to-end hashes before operational use.
