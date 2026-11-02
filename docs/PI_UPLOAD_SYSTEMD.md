# Pi private upload recovery: systemd deployment

This is a deployment template, **not an installed service**. It must be
tested on the Raspberry Pi before enabling it in production.

1. Create a dedicated unprivileged `kidsstudio` user and install the
   repository and Python dependencies at `/opt/kidsstudio`.
2. Create `/var/lib/kidsstudio/private-upload` and
   `/var/lib/kidsstudio/secrets` owned by that user, mode 0700.
3. Place OAuth credentials in `/var/lib/kidsstudio/secrets/youtube.json`,
   owner `kidsstudio`, mode 0600. Never commit this file.
4. Check that the user can read the saved session's video path.
5. Copy `deploy/systemd/kidsstudio-pi-upload.service` to
   `/etc/systemd/system/`, then run `sudo systemctl daemon-reload`.
6. Test once manually with `python -m kidsstudio.pi_upload_service
   --state-dir /var/lib/kidsstudio/private-upload --credentials
   /var/lib/kidsstudio/secrets/youtube.json --once`.
7. Only after a successful private upload test, enable with
   `sudo systemctl enable --now kidsstudio-pi-upload.service`.

The worker uses a nonblocking file lock to prevent concurrent workers,
requeues interrupted jobs at startup and polls the SQLite queue. Failed
jobs remain failed; no automatic public publishing is possible.

**Caveats:** the initial upload must first create and enqueue a resumable
session. This service handles recovery jobs only. Uploads are not yet
end-to-end tested, and OAuth credentials must be provisioned by the
owner. Network access and any external media mount paths must be
validated against systemd sandbox restrictions.
