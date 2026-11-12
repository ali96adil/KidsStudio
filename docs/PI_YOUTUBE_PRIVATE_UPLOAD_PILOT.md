# Raspberry Pi — YouTube PRIVATE resumable upload pilot (operator-only)

> **PRIVATE draft first, owner review second (Batch 60):** an authenticated explicit PRIVATE upload may happen after automated technical SHA/codec checks and verified Pi receipt, even before the owner watches the video. The owner reviews the resulting PRIVATE YouTube draft and decides on revision or later **separate** public publication. The OAuth/upload capability still requires explicit user consent and remains untested with real credentials.

**Status:** explicit foreground uploader implementation with mock-tested Google API interactions. The Pi has NOT used it with real credentials. It has NOT uploaded a real video. No unattended publishing service or public release is implemented.

Official APIs consulted:
- https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol
- https://developers.google.com/youtube/data/reference/rest/v3/videos/insert
- https://developers.google.com/youtube/data/guides/authentication

## Safety and behavior

- No API call occurs without all three local CLI flags: `--execute-private-upload`, `--owner-authorized`, `--confirm-made-for-kids`. **These flags are operator assertions, not cryptographic proof of owner identity.** Only use them under the owner's supervision.
- The YouTube request explicitly sets `privacyStatus=private` and `selfDeclaredMadeForKids=true`, and disables new subscriber notifications. It never sends a public scheduling field and never calls the videos.update/publication API. The made-for-kids setting is appropriate only after reviewing the actual intended audience.
- Checks the locally staged media SHA256 and private permissions before any contact with Google. It uses fixed, TLS-validated Google OAuth / YouTube API hosts. No third-party destinations, dynamic redirects, or arbitrary URLs.
- OAuth client ID/secret and refresh token are read from a **pre-existing local 0600 JSON file** in a private 0700 directory outside Git. A dedicated, manually provisioned, least-privilege Google OAuth client with the youtube.upload scope and owner consent is a prerequisite. This module **does not implement initial OAuth authorization or Google account creation**. Never paste credentials into chat, Git, CI logs or shell command arguments.
- OAuth access tokens are refreshed automatically *in memory* by the Google refresh-token endpoint, but secrets are never logged or written to the upload journal.
- Each upload uses a **persistent private journal**. A brand-new journal is written **before** the first session-initiation HTTP call. If a failure happens between API session creation and journal persistence, state stays `INITIATION_UNCERTAIN`; **do not automatically start another upload**, as a duplicate might result. Reconcile manually on YouTube Studio and inspect the private journal.
- Saved resumable session URLs are sensitive, kept in the 0600 local journal, and never printed. Restarting with the identical request **probes the existing session** to discover the server-acknowledged offset before sending more bytes. A session error/expiry is not silently replaced. Operators must reconcile uncertain remote uploads before preparing a brand-new journal.
- Content is streamed as 1MiB chunks, preventing full-MP4 RAM loading; each foreground invocation handles up to 4096 chunks by default and then returns `UPLOAD_PAUSED_RESUMABLE` to be explicitly resumed with the same exact command. The Pi can upload without keeping the Mac on.
- When a final upload response is received, the tool checks the local file digest again and separately reads the real remote video status with the same OAuth credentials. Only `privacyStatus=private` becomes `PRIVATE_UPLOAD_CONFIRMED`. A failed remote confirmation is persisted as `REMOTE_COMPLETED_UNVERIFIED` for manual investigation; it never re-uploads automatically.
- Even `PRIVATE_UPLOAD_CONFIRMED` is **not approval to make the video public**. The owner still reviews the PRIVATE draft, gives feedback and separately decides on publication.

This is a new privileged network capability in a *draft* PR; do not run against production media until security review and controlled qualification are complete. There is no background/daemon deployment or automatic queue polling.

## Supervised Pi-only setup (not executed here)

1. On the Pi, use a separate user-owned private location with permissions `0700` for credentials, journals and media. **The currently verified Mac→Pi file transfer must be completed separately**. Run the read-only SHA checks and confirm same Git source revision before upload.
2. Create a Google OAuth client for an installed application and authorize the correct YouTube channel using the `https://www.googleapis.com/auth/youtube.upload` permission. Obtain a refresh token through an owner-controlled approved OAuth process. Check Google API quota and testing/publishing status of the OAuth app. **Initial OAuth login is a separate prerequisite.**
3. Store credentials as a local file, e.g. `$HOME/kidsstudio-private/credentials/youtube-oauth.json` with mode `0600`:

~~~json
{
  "client_id": "REPLACE_WITH_YOUR_OAUTH_CLIENT_ID",
  "client_secret": "REPLACE_WITH_YOUR_OAUTH_CLIENT_SECRET",
  "refresh_token": "REPLACE_WITH_YOUR_OWN_REFRESH_TOKEN"
}
~~~

Do not commit that file. Store the journal under a **different** private folder. Make both parent directories mode 0700. Do not use the example credential strings in a real run.

4. For a reviewed, rights-cleared synthetic pilot MP4 on the Pi, independently calculate the SHA256 and use a **unique new journal filename per episode and version**. Example only:

~~~bash
python -m kidsstudio.pi_youtube_private_upload \
  --private-root "$HOME/kidsstudio-private/inbox" \
  --relative-path episode-test.mp4 \
  --expected-sha256 YOUR_VERIFIED_SHA256 \
  --episode-id colors_ar_test_001 \
  --title "تعلّم الألوان – نسخة اختبار خاصة" \
  --language ar \
  --journal "$HOME/kidsstudio-private/journals/colors-ar-test-001.json" \
  --oauth-json "$HOME/kidsstudio-private/credentials/youtube-oauth.json" \
  --execute-private-upload \
  --owner-authorized \
  --confirm-made-for-kids
~~~

**Important:** The above command makes REAL network calls and submits a real PRIVATE video when configured correctly. Only an operator with the owner's explicit consent should run it. Running the module *without* `--execute-private-upload` returns `NOT_EXECUTED` with zero network activity. There is no CLI-only automatic setup or real upload in GitHub CI.

5. On timeout or network failure, **do not delete/rename the journal and retry as new**. Review its state. For `SESSION_ACTIVE`, rerun the exact same command after checking the network; it asks the existing Google session what bytes were already stored. For `INITIATION_UNCERTAIN`, do not retry as new automatically: inspect YouTube Studio and reconcile. For `REMOTE_COMPLETED_UNVERIFIED`, it only rechecks privacy on the already uploaded video. For `PRIVATE_UPLOAD_CONFIRMED`, rerunning is idempotent (no new Google upload). Do not share journal content or credentials.

## Remaining qualification gates before enabling unattended service

- **Real Pi pilot**: complete OAuth consent, confirm channel identity and billing/quota, transfer and verify an actual rights-cleared test MP4, observe resumed upload after network disconnect, and verify the video is visible in YouTube Studio as PRIVATE.
- **Security hardening review:** journal persistence under crash/power loss, network timeout and untrusted server responses, lock-file recovery, exact MIME/content type, token handling and independently verifying target channel/video content.
- **Owner review:** open and watch the PRIVATE draft; check correct Arabic/English voice, timing and educational content before release.
- **Optional later automation:** queue consumer, secure Mac→Pi transport, service restart, OAuth enrollment, fully supervised privacy audit and separate owner-governed publication. These are NOT part of this pilot.

## Batch 59 — offline end-to-end smoke before live OAuth

GitHub CI now runs the real first-colors 24-second FFmpeg MP4 all the way through Mac private sidecar creation, an explicitly **simulated** owner acceptance, the existing reviewed-transfer gate, the Pi receiver *in-process* on a temporary private folder, and the **real resumable uploader implementation with an injected FAKE Google backend and token**. It verifies exact bytes and SHA across the mock Mac/Pi boundary, the final private-only fake upload response and the journal's confirmed state. The fake backend refuses `public`, `unlisted`, missing `selfDeclaredMadeForKids`, or `publishAt` metadata in tests.

This test must never be called a real YouTube upload or a real user review: no DNS, SSH, Google OAuth credentials, network traffic or persistent CI media are involved, and the fake video ID is not a YouTube resource. The Pi's genuine Google OAuth and actual PRIVATE upload **still require an explicit supervised device test** following the independent Mac/Pi receipt verification procedure.

## Batch 60 — human review AFTER YouTube PRIVATE upload

The intended KidsStudio flow is **automated technical QC on Mac → securely stage SHA-checked video on Pi → upload an authorized PRIVATE YouTube draft → owner watches/reviews that PRIVATE draft and records notes**. A pre-YouTube `ACCEPTED_PRIVATE` manual review note is **not required** to stage technical QA-passed content on Pi. This distinction is important: `private` is a visibility state, not publication approval. The uploader already forces `privacyStatus=private`, `selfDeclaredMadeForKids=true`, no public scheduling, and explicit operator authorization; the user must independently authorize Google OAuth first and verify the correct channel/audience.

`scripts/ci_full_private_chain_smoke.py` now tests this correct order on a real locally encoded MP4: it mocks only host role, Pi SSH network and Google service; it does **not** create a fake pre-upload owner approval. It records a simulated revision note **after** fake private upload solely to verify program flow (no one actually watched the video). No actual YouTube account is contacted, no media is uploaded and no public release occurs.

## Batch 63 — keep exact private upload journal for post-upload review

New PRIVATE upload journals now also persist the exact `media_name` and `episode_id` alongside the immutable upload intent fingerprint, SHA256/size and confirmed video ID. Once the real upload returns `PRIVATE_UPLOAD_CONFIRMED`, the owner can open that exact video in YouTube Studio and use the read-only `kidsstudio.pi_private_draft_review` command to match the video ID to the preserved journal and Pi media. A separate, explicit note-writing command accepts either REVISION_REQUIRED with notes or ACCEPTED_PRIVATE after full video + Arabic voice listening assertions, and saves a private file bound to the exact version. **This is not a privacy-status API query or public approval.** See [PI_PRIVATE_DRAFT_OWNER_REVIEW.md](PI_PRIVATE_DRAFT_OWNER_REVIEW.md). Old journals without the new fields require manual reconciliation; do not invent upload metadata or reset uncertain upload journals to make a review pass.
