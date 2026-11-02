# Pi private-upload receipt boundary

After the authenticated Pi uploader successfully uploads a video as
**private**, it may call `record_private_upload` with a receipt containing:

```json
{
  "privacy": "private",
  "upload_succeeded": true,
  "video_id": "Abc123_defG",
  "channel_id": "YOUR_CHANNEL_ID",
  "media_sha256": "64 lowercase hex characters"
}
```

The recorder checks receipt fields, verifies the current local video hash,
and inserts an append-only binding in SQLite. Public/unlisted/failed uploads,
wrong channels and mismatched digests are rejected.

**Trust boundary:** This is a validation/recording component, not an
authenticated YouTube upload implementation. The receipt must originate from
a trusted uploader and must not be accepted from an arbitrary browser or
external request. A caller-provided `upload_succeeded` flag alone is not
proof of YouTube state. Production integration must obtain the video ID from
the actual successful YouTube upload response and independently inspect the
video via YouTube Data API.

No module here can change a YouTube video's privacy.
