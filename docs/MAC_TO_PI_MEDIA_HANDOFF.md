# Mac render to Raspberry Pi: secure media handoff

Mac renders the episode to MP4. `build_manifest(video, episode_id)`
records the file size and SHA-256. `transfer_to_pi(..., dry_run=False)`
copies the MP4 and manifest over SSH/rsync to a Pi staging directory.
Dry-run is the default.

On the Pi, `ingest_media(source, manifest, inbox)` verifies the exact
size and SHA-256 and atomically moves a verified copy into the inbox.
A failed verification never places a video in the final inbox.

**Integration still needed:** a Pi staging watcher must match transferred
manifest and MP4 files, call `ingest_media`, then create a resumable
YouTube upload session and enqueue the corresponding job. The Mac
transfer helper does not itself start a YouTube upload.

Use dedicated SSH keys with least privilege and a fixed staging path.
Do not accept untrusted SSH destinations or arbitrary remote paths.
No YouTube credentials should be copied to the Mac. YouTube uploads
must remain private until explicit owner review and authorization.
