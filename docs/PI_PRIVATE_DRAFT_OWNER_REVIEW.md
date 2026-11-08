# KidsStudio — review the exact YouTube PRIVATE draft after upload

The intended first-episode order is **Mac local technical QA → verified Pi inbox → separately authorized YouTube PRIVATE upload → owner watches the PRIVATE draft in YouTube Studio → local written review or revision → independent later public-release decision**.

**This is an offline note-taking feature.** It does not call Google, log in, query current video privacy, edit YouTube metadata, transfer video files or publish anything. Its only file write is an opt-in new owner-private review JSON. CI has not used real user hardware, credentials, channel, or a real video.

## Prerequisites

The Pi's actual PRIVATE uploader must have finished with status PRIVATE_UPLOAD_CONFIRMED. Its private mode-0600 upload journal must still be saved with the same SHA-256 and new version-binding fields (media_name, episode_id and video_id). INITIATION_UNCERTAIN, SESSION_ACTIVE and REMOTE_COMPLETED_UNVERIFIED are **not enough**: reconcile those according to PI_YOUTUBE_PRIVATE_UPLOAD_PILOT.md first, do not make a replacement upload blindly.

On the Pi, use the confirmed video in **YouTube Studio**, and obtain its exact video ID. Check manually that the video is currently visible **only as PRIVATE**, and watch/listen to the whole actual draft. A local historical upload journal does NOT prove that a video remains private right now or that the viewer is authenticated. Keep the uploaded video's ID, the Pi inbox MP4's **trusted original SHA**, and the journal's filename together.

Prepare a private review-note directory on the Pi:

~~~bash
umask 077
mkdir -p "$HOME/kidsstudio-private/reviews"
chmod 700 "$HOME/kidsstudio-private/reviews"
~~~

## Read-only eligibility check: no review is written

Replace every placeholder with the exact source file, 64-digit Mac/Pi SHA, unique upload journal and video ID copied from the SAME YouTube Studio PRIVATE draft:

~~~bash
python3 -m kidsstudio.pi_private_draft_review \
  --private-root "$HOME/kidsstudio-private/inbox" \
  --relative-path ACTUAL_COLORS_EPISODE.mp4 \
  --expected-sha256 EXACT_TRUSTED_SHA256 \
  --episode-id colors_ar_01 \
  --journal "$HOME/kidsstudio-private/journals/ACTUAL_JOURNAL.json" \
  --video-id EXACT_VIDEO_ID_FROM_YOUTUBE_STUDIO
~~~

The returned status PI_PRIVATE_DRAFT_REVIEW_ELIGIBLE_OFFLINE means only: Pi file SHA/bytes and private permissions match a local **previously PRIVATE-confirmed** journal for that exact original episode and remote video ID. This is a historical local proof: **no live Google call was made**. Without --save-review, no notes or changes are created.

## Save explicit owner notes AFTER reviewing YouTube PRIVATE

To request a **new version**, repeat the same exact arguments and append:

~~~bash
  --review-root "$HOME/kidsstudio-private/reviews" \
  --review-outcome REVISION_REQUIRED \
  --reviewer-notes "Replace the issue at 00:12 and correct Arabic voice" \
  --reviewed-private-draft \
  --save-review
~~~

To accept the **private draft only**, repeat the same exact arguments and append:

~~~bash
  --review-root "$HOME/kidsstudio-private/reviews" \
  --review-outcome ACCEPTED_PRIVATE \
  --reviewer-notes "Checked entire PRIVATE YouTube draft" \
  --reviewed-private-draft \
  --reviewed-full-video \
  --reviewed-arabic-voice \
  --save-review
~~~

These fragments are appended to the full inspection command. The flags are **operator assertions, not authenticated video-watching proof**. Revision requires a nonblank note; acceptance requires explicit assertions of having watched the entire draft and listened to all Arabic speech. Neither outcome ever grants permission to make the upload PUBLIC. If any revision has been filed for the same video ID/SHA, the tool refuses subsequent acceptance for that **same** version: produce/upload/review a new version instead.

Every record is a separate mode-0600 JSON outside Git with the exact video ID, original SHA, original episode, unique upload intent fingerprint, result and notes. Existing notes are not overwritten. The code rejects untrusted, conflicting or world-readable review-shaped records; it does **not** claim cryptographic owner identity or tamperproof local storage. Never put these notes, media or upload journals in GitHub issues, CI artifacts, or public dashboards.

## What this does not do

This tool does not set, schedule or update YouTube visibility and never issues an upload. ACCEPTED_PRIVATE is not a publication credential. You must separately decide on public release after completing any channel/content policy review. Automated CI checks with a *fake* YouTube provider only prove local end-to-end code wiring, not privacy status, Arabic pronunciation or user approval.

## Batch 64 — one-command local PRIVATE drafts inbox (read-only)

On the Pi, after creating your existing owner-only `inbox`, `journals` and `reviews` directories, run:

~~~bash
python3 -m kidsstudio.pi_private_draft_inbox
~~~

This displays a **terminal status board**, generated ONLY from existing private upload journals, current SHA-verified Pi MP4 files, and the exact review notes recorded by `pi_private_draft_review`. It can show `NEEDS REVIEW`, `REVISION`, `ACCEPTED PRIVATE`, `UPLOAD UNCERTAIN` or `BLOCKED`. It never contacts YouTube or SSH, changes a file, resumes an upload, or grants public publication permission. The table does not print OAuth secrets, resumable session URLs, review-note text, or video IDs.

For a JSON overview:

~~~bash
python3 -m kidsstudio.pi_private_draft_inbox --format json
~~~

For a deliberate **local** inspection including the exact private YouTube video IDs, use `--format json --show-video-ids`. Avoid pasting that output into public logs. Multi-version episodes stay separate by exact upload journal, video ID, original source SHA and review-note binding. Any revision note takes priority over older local acceptance notes for the same version.

The board uses **historical local PRIVATE-confirmed upload evidence only**, not the current YouTube visibility. Verify PRIVATE status in YouTube Studio before clicking on a video, and treat accepted private notes as human *assertions*, not authenticated public publication authority. If the tool prints `BLOCKED`, the media, journal, or review note failed local validation. Do **not** delete or reset a journal and retry Google to make the board green; investigate evidence safely and reconcile ambiguous uploads manually.
