# Recover a private YouTube upload after Pi restart

The uploader can persist its resumable session after `start_session`:

```python
from kidsstudio.youtube_upload_session import save_session
save_session("~/example-session.json", session_url=session_url, video_path=video_path)
```

Use an expanded path or `Path.home()` in real code; the example above is
illustrative. The session URL is sensitive: keep the JSON in a private
directory outside GitHub. The file is atomically written with mode 0600.

On restart, `resume_saved_upload(session_path, access_token)` verifies the
file's SHA-256 and size, queries YouTube's authoritative upload offset,
then resumes from the offset returned by YouTube. The local stored offset
is **never** trusted as the server's progress.

Current limitations: no automated retry/backoff or persistent retry
scheduler; no OAuth token refresh during a long upload; no automatic
session expiry handling; no atomic linkage to the actual upload receipt
ledger; and no live end-to-end YouTube test. Session URL handling should
be treated as secret material. This recovery code never publishes a video.
