# Pi upload recovery with fresh OAuth tokens

`FileTokenProvider` reads a mode-0600 OAuth credential file outside
the repository and obtains a short-lived access token. Never log or
commit credentials.

`supervise_resume` validates the saved media session, refreshes an
access token before each attempt, then resumes a private YouTube upload.
Transient failures use bounded exponential backoff. Permanent errors,
including a changed video file, stop without retries.

Example integration (inside a trusted Pi worker):

```python
from kidsstudio.pi_upload_token_provider import FileTokenProvider
from kidsstudio.pi_upload_supervisor import supervise_resume
from kidsstudio.youtube_upload_binding import UploadBindingStore

bindings = UploadBindingStore("/var/lib/kidsstudio/uploads.sqlite")
bindings.initialize()
result = supervise_resume(
    bindings,
    episode_id="red-ar",
    session_path="/var/lib/kidsstudio/upload-session.json",
    expected_channel_id="YOUR_CHANNEL_ID",
    token_provider=FileTokenProvider("/var/lib/kidsstudio/secrets/youtube.json"),
)
```

**Limits:** tokens are refreshed between attempts, not during one long
attempt; an expired token may interrupt that attempt. The worker is not
yet a systemd service or durable queue processor. Live OAuth authorization,
YouTube uploads and reboot recovery still need on-device verification.
No public visibility changes are performed.
