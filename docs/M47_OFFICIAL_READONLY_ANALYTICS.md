# M47 — Official read-only YouTube Analytics collection

Status: GitHub DRAFT PR #28. NO owner Mac/Pi installation, account connection, model inference, API query, OAuth request or video publication occurred. CI uses FAKE HTTP responses, not real channel metrics.

## Why this stage exists

M15 could compare educational video performance, but required manual owner-prepared metric files. The new studio-analytics-collect reads a private owner-reviewed profile plan and may, ONLY with --execute and an owner-provided short-lived OAuth token, query the official read-only YouTube Analytics Reports endpoint.

Reference: https://developers.google.com/youtube/analytics/reference/reports/query

Fixed secure endpoint: https://youtubeanalytics.googleapis.com/v2/reports. Every GET pins the exact provided channel ID (channel==UC...) and exactly one validated 11-character video ID. It requests seven calendar days inclusive of publication through day six, only at least ten days after publication. At most eight requests per batch. No arbitrary host, redirects, POST, payment, upload, user demographics or child personal data.

Requested non-monetary metrics: views, estimatedMinutesWatched, averageViewDuration, averageViewPercentage. API response column names, shape and numeric bounds are checked. Empty/suppressed rows remain missing; zero views are never invented. Repeat viewing may create an averageViewPercentage greater than 100; values through 400 are retained to avoid misclassifying Shorts.

Important: this Reports API query DOES NOT give thumbnail impressions/CTR. M47 stores impressions=0 with CTR=null as an UNAVAILABLE-DATA compatibility representation, NOT a measured zero. M15 cannot call a long-form style the winner with only these metrics because long-form needs independently measured thumbnail impressions. Shorts can be compared on retention and views without that field.

## Security, ownership and provenance

The private plan contains schema_version=1, channel_id and 1–8 profiles with the exact M15 profile fields: series/episode, video ID, language, short/long format, duration, publication date, four creative style tags and owner_education_verified. Each is independently checked against approved Studio Brain episodes and language. These tags describe owner-verified original content.

The Google documentation currently notes the youtube.readonly scope in addition to the documented yt-analytics.readonly Analytics scope. Actual owner OAuth setup is NOT built or tested here. Google must authenticate the pinned channel. Never paste a token into chat, command arguments, repository files or CI. KIDS_STUDIO_YT_ANALYTICS_TOKEN is read at execution time only, and is never printed or saved.

Default command is read-only, DOES NOT contact Google, does not need a token and writes no files. --execute requires a NEW mode-0600 private JSON destination. The output is labelled OWNER_AUTHORIZED_YOUTUBE_ANALYTICS_API_READONLY; it is not an owner-confirmed manual Studio export. Collection never imports metrics automatically, edits scripts, runs models, uploads a video, or authorizes public release.

## Later operator procedure, only after owner authorization

Plan only:

    studio-analytics-collect --db /PRIVATE/studio.sqlite --profiles /PRIVATE/profiles.json --channel-id UCXXXXXXXXXXXXXXXXXXXXXX

Explicit GET collection after read-only OAuth:

    studio-analytics-collect --db /PRIVATE/studio.sqlite --profiles /PRIVATE/profiles.json --channel-id UCXXXXXXXXXXXXXXXXXXXXXX --execute --out /PRIVATE/analytics/week01.json

Separately review and import:

    studio-learning --db /PRIVATE/studio.sqlite import --file /PRIVATE/analytics/week01.json
    studio-learning --db /PRIVATE/studio.sqlite analyze --series colors-ar

M15 compares only comparable same-series, language, format and publication-age videos and proposes observational hypotheses. The owner still must adopt an experiment; existing scripts/media are immutable and educational, age safety and rights standards stay mandatory.

## Tests and remaining blockers

Mocked official report rows cover exact channel and video filters, date range, no-network default, invalid/missing/suppressed metrics, unavailable reach, duplicates, wrong channel, wrong owner episode, missing token, redirected host and immutable M15 import. No actual Analytics account data was accessed.

Real owner account OAuth, M46 true Apple MPS compatibility and actual model training/inference quality, full two-scene private video, voice/animation licensing, independent backup restore and final owner post-private-upload review remain outstanding. PR remains DRAFT/unmerged; no device deployment.
