# Pi YouTube release preflight

This is a **read-only** diagnostic. It refreshes an OAuth access token,
reads the actual YouTube video privacy/channel via YouTube Data API, and
checks the latest local owner review and release authorization.

After completing the separate OAuth authorization flow, create a file
**outside the Git repository** (for example `~/kidsstudio-secrets/youtube.json`)
containing exactly these keys:

```json
{
  "client_id": "YOUR_OAUTH_CLIENT_ID",
  "client_secret": "YOUR_OAUTH_CLIENT_SECRET",
  "refresh_token": "YOUR_OAUTH_REFRESH_TOKEN",
  "channel_id": "YOUR_EXPECTED_CHANNEL_ID"
}
```

Protect it: `chmod 600 ~/kidsstudio-secrets/youtube.json`. Never commit,
share, or paste real credentials into chat. Run as the file owner:

```bash
python -m kidsstudio.pi_youtube_release_check \
  --credentials ~/kidsstudio-secrets/youtube.json \
  --review-db ~/kidsstudio-data/reviews.sqlite \
  --release-db ~/kidsstudio-data/release.sqlite \
  --episode red-ar \
  --video-id YOUR_11_CHARACTER_VIDEO_ID
```

The result describes readiness for **manual release only**. It cannot
change video visibility. A matching channel ID is necessary but not a
complete proof of a video's authorized episode mapping. No live YouTube
account has been connected or tested as part of this implementation.

The OAuth consent/bootstrap flow remains a separate prerequisite.
