# Pi resumable YouTube upload transport

`kidsstudio.youtube_resumable_upload` implements the low-level YouTube
Data API resumable upload protocol for MP4 videos.

- `start_session(access_token, video_size, title, description)` initializes
  an upload with **private** visibility and a self-declared made-for-kids
  flag. The latter is a metadata decision, not a substitute for the
  owner's content classification and review.
- `upload_chunk(session_url, access_token, payload, start, total)` sends
  a chunk and interprets HTTP 308 acknowledged ranges.
- `upload_video(session_url, access_token, video_path, offset=0)`
  transfers chunks and requires a private completion receipt.

**Not production-ready yet:** session URL and offset persistence, querying
server progress after network interruption, token refresh during multi-hour
uploads, retry/backoff for 429/5xx, post-upload API verification, secure
channel-specific OAuth setup, and the actual Pi uploader integration still
need implementation and live tests. Do not assume a network interruption
will resume automatically. Never log the session URL: it is a sensitive
upload capability.

No operation changes an existing video's visibility to public.
