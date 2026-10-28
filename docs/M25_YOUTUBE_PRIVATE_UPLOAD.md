# M25 — YouTube API PRIVATE upload; exact master, durable no-repeat fence

**Status:** code and synthetic offline tests on GitHub Draft PR #28;
not installed on owner devices, not authenticated to the owner's
Google/YouTube account, no upload attempted and no media published.

## Actual YouTube protocol (documented at Google)

- YouTube Data API `videos.insert` supports resumable upload; clients
  must explicitly set `status.privacyStatus="private"`. The default
  can be public if omitted. The payload also explicitly carries
  `status.selfDeclaredMadeForKids` (after correctly assessing intended
  audience) and `status.containsSyntheticMedia`. These booleans
  are owner-pinned values, not guessed at runtime.
- A successful upload yields an exact 11-character video ID. The
  uploader then calls authenticated `videos.list` with
  `part=snippet,status,processingDetails`, checks the ID, exact
  intended channel ID, `status.privacyStatus="private"` and
  `processingDetails.processingStatus="succeeded"` before marking the
  video ready for owner review.
- If the video's processing is still underway, the uploader returns
  `YOUTUBE_PRIVATE_PROCESSING_PENDING`; a separate
  `--verify-existing` invocation looks up the **same video ID**
  WITHOUT `videos.insert`. No auto-duplicate upload is permitted.
- The transport accepts only `https://www.googleapis.com`, with
  fixed API paths, verified TLS, zero redirects and bounded response
  lengths. Resumable session URI host and path are strictly checked.
  The uploader uses 8 MiB chunks, acknowledgments with exact byte
  ranges, and no retry after an ambiguous network error.
- Google access is through an OAuth 2.0 **access token** the owner
  separately obtains and explicitly supplies in a private environment
  variable. This repo does **not** currently implement OAuth consent,
  refresh-token encryption/rotation or a YouTube channel onboarding UI.
  Upload rights must be set up legitimately and the Google API project
  must meet YouTube API verification/compliance requirements.
- This implementation has **no** `videos.update`, no
  `status.privacyStatus="public"`, no `publishAt` and no
  scheduled publishing option. Even an accepted review is not a
  Public operation.

Current docs:
- `https://developers.google.com/youtube/data/reference/rest/v3/videos/insert`
- `https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol`
- `https://developers.google.com/youtube/data/reference/rest/v3/videos/list`
- `https://developers.google.com/youtube/terms/developer-policies`

## Source-of-truth and owner action

The Mac takes an **explicit private JSON upload plan**, its exact
final MP4 and pinned M8 archive/readiness report.
The report must contain `READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED`,
match the same approved episode, render job, media SHA, final owner QA,
and assert publication not authorized. The MP4 must have the exact
owner-approved SHA before any network connection. Upload plan example:

```json
{
  "schema_version": 1,
  "series_id": "colors-ar",
  "episode_number": 1,
  "render_job_id": "11111111111111111111111111111111",
  "master_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "target_channel_id": "UCqqqqqqqqqqqqqqqqqqqqqq",
  "title": "Original color-learning episode",
  "description": "Educational video",
  "category_id": "27",
  "made_for_kids": true,
  "contains_synthetic_media": true
}
```

Identifiers above are placeholders, never the user's actual channel,
OAuth token or creative assets. For YouTube Kids, marking
`made_for_kids` appropriately is mandatory according to the
actual intended audience; it does **not** guarantee distribution in
the YouTube Kids app or monetization.

A dry-run/preflight has **no network**, requires no OAuth token:

```sh
studio-youtube-private-upload \
  --plan /PRIVATE/upload_plan.json \
  --media /PRIVATE/episode_master.mp4 \
  --readiness /PRIVATE/M8_ready.json \
  --readiness-sha256 EXACT_M8_REPORT_SHA256
```

The real upload additionally requires explicit `--execute`,
`--journal /PRIVATE/upload_attempts.sqlite`, and an OAuth bearer token
available only from `KIDS_STUDIO_YOUTUBE_OAUTH_ACCESS_TOKEN`
(or explicitly selected private env var). **Do not execute yet**.
The Mac persists `STARTED` before requesting a resumable session;
if power/network fails, it will NOT run a second `videos.insert`
for the same job or master SHA. The user must reconcile ambiguous
state manually using YouTube Studio before any further action.
The journal is outside Git, uses SQLite FULL synchronous commits,
and stores no token or bearer session URL.

An explicit later `--execute --verify-existing` (same other CLI args)
re-checks an already-returned ID when the journal state is
`UPLOADED_UNVERIFIED` or `PRIVATE_VERIFIED`. It does not re-upload.

## Import verified result to the Pi's M24 review workflow

After authenticated YouTube `videos.list` confirms **Private +
processing succeeded**, the Mac prints a simple JSON receipt:
`YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING`. Owner can save it
as a private JSON file, transmit it by a trusted private path and
register it with its exact SHA256 on Pi:

```sh
studio-preview-review --db /PRIVATE/pi-brain.sqlite \
  import-youtube-report --report /PRIVATE/m25_private_api_result.json \
  --sha256 EXACT_M25_RESULT_FILE_SHA256
```

M24 verifies the report's exact schema, that the ID, hash and
render job still match the locally approved Pi master, that the
reported API check was private with processing succeeded, and
that the report does **not** authorize public release.
The video then appears in the protected owner review UI, with
a visibly distinct status from a manually reported private upload.

This is a **locally imported API report, not a cryptographic signature
by Google**. It attests a successful API response only if the owner
can trust the Mac process, secure file transfer and report origin;
a malicious forged JSON file would not independently prove YouTube
privacy. A separate live API recheck immediately before any future
publication is still required.

## Tests / limits

GitHub synthetic tests verify exact PRIVATE metadata + audience and
synthetic media flags, successful fake resumable upload, 308 strict
range handling, URL/host restrictions, stale M8 plan/bad MP4 rejection,
ambiguous start/PUT quarantine, no duplicated upload for a repeated
master, processing-pending/reverify-only behavior, wrong public
privacy/channel rejection, dry-run without credentials, Pi M24 exact
receipt import, and no PUBLIC/publishAt request path.

**This is M25's first opt-in uploading adapter, not a deployed studio
uploader or YouTube production qualification.** It does not implement
automated OAuth provisioning, upload resume after a half-sent chunk
(the attempt stays quarantined), detailed quota/backoff, thumbnail or
captions uploads, private video accessibility to other accounts,
or a separate authorization to set Public.
