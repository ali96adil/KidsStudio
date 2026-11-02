# Pi staging to private YouTube upload queue

`prepare_private_upload` connects the Mac media transfer and the Pi
upload worker. It reads a staged JSON manifest, verifies the transferred
MP4's SHA-256, atomically copies it into the Pi inbox, creates a private
YouTube resumable session, persists that session, and queues it for the
existing systemd worker.

A session with the same episode and media digest is not silently
re-created. This prevents ordinary duplicate submissions; operators
must inspect and recover interrupted sessions rather than delete state.

The function expects trusted metadata (title, channel ID, OAuth token)
from the production scheduler. It is **not** a network-facing upload
endpoint or a staging directory watcher. The watcher, title metadata
source, full end-to-end integration, OAuth setup, and physical Pi
verification still need work. Videos are never made public here.
