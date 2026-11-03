# Mac → Pi verified transfer

Run from the Mac checkout of KidsStudio, with the same KidsStudio Python
package installed on the Pi and SSH key-based access configured.

Dry run (no SSH, no transfer):

```bash
python3 -m kidsstudio.mac_pi_verified_transfer \
  --video /path/to/render.mp4 \
  --episode-id colors_001 \
  --ssh-target pi@raspberrypi.local \
  --remote-staging-dir /home/pi/kidsstudio/staging
```

When ready to perform the actual rsync and remote SHA-256/size verification,
repeat with `--execute`. The remote Pi runs
`python3 -m kidsstudio.pi_received_media_precheck` and returns a JSON report.
A failed transfer, invalid report, or digest mismatch makes the command fail.
Keep the Pi staging directory writable by the SSH account and configured for
the Pi watcher. The manifest is published last via a remote rename.

**Safety:** This command never starts a YouTube upload, never queues an upload,
and never authorizes a public release. A passing mocked CI test does not
replace a real hardware acceptance test on Mac and Pi. The original source
must remain unchanged during transfer and verification; if it changes,
verification fails.
