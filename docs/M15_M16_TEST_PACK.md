# Kids Studio M15/M16: Learning and Testing Plan

Status: development on DRAFT PR 28, not deployed. No owner Mac/Pi installation, live AI inference, paid API, upload or YouTube publication.

## M15: data-driven learning, without losing educational value

The local studio-learning command extends canonical Studio Brain SQLite. It imports an explicitly owner-verified structured, private JSON export containing video IDs, episode IDs, language, format, publication date, creative tags and seven-day performance snapshots. The source label OWNER_VERIFIED_YOUTUBE_STUDIO_EXPORT is an owner assertion, not OAuth authentication or proof from YouTube.

Creative tags describe what was actually made: hook_style, story_style, pace_style and participation_style. Outcome observations may include views, thumbnail impressions, click-through rate, average-view percentage, average-view duration and minutes watched, with unavailable metrics marked null. Keep private sample data out of public GitHub.

To suggest a style, M15 compares only same-series, same-language, same-format, similar-age-of-publication cohorts. It requires at least three videos per style, 300 total views each, measured retention; long videos additionally need 2000 thumbnail impressions each. Shorts can have missing thumbnail impressions or CTR; their comparisons can use views and retention. The proposed winner must have at least eight percentage points higher median average-view percentage AND 1.15x median views-per-day. Such a suggestion is observational, not a causal result or proven formula for viral success.

YouTube restricts some audience metrics for Made for Kids videos and small samples. Missing demographics or reach are not evidence of failure. The current M15 comparison does not parse moment-by-moment retention curves or automatically download reports. Those can be future, owner-authorized enhancements.

The owner explicitly adopts or rejects each proposal with a substantive educational/rights note. An adopted proposal appears as an OPTIONAL hypothesis in the next original script-draft brief. Approved scripts, child-safety review, existing media and public release state are not changed. Avoid repetitive clickbait and copying popular children's videos.

Future commands, after explicit deployment approval:

    studio-learning --db /PRIVATE/brain.sqlite init

    studio-learning --db /PRIVATE/brain.sqlite import --file /PRIVATE/owner_verified_metrics.json

    studio-learning --db /PRIVATE/brain.sqlite status --series colors-ar

    studio-learning --db /PRIVATE/brain.sqlite decide --proposal-id EXACT_ID --decision ADOPT_FOR_FUTURE_EXPERIMENT --owner-note "Try a question-based intro only when it improves original, correct learning; human review remains mandatory."

The Arabic read-only dashboard summarizes proposals and approved experiments. It cannot approve changes or publish.

Official references:
https://developers.google.com/youtube/analytics/metrics
https://developers.google.com/youtube/analytics/reference/reports/query
https://support.google.com/youtube/answer/9314415
https://support.google.com/youtube/answer/9101241

## M16: exact Pi-to-Mac catalogue pin

M14 freezes M13 approved scene media and writes a pinned Mac media catalogue. A multi-scene episode_assemble job on Pi now requires an exact catalogue_sha256. The Mac worker compares it to the complete local MediaRecipes catalogue SHA before executing. M14 also independently checks media identities, current WAV/LTX hashes, scene order and local receipts. Wrong digest is rejected before the executor starts. The Pi still sends only an allowlisted recipe ID, approved script SHA and catalogue SHA. No shell commands or arbitrary paths travel in the job.

Future owner command, after catalogue was created and checked:

    python -m kidsstudio.series_cli --db /PRIVATE/brain.sqlite queue-render colors-ar 1 --recipe colors_ar_ep01_v1 --media-kind episode_assemble --catalogue-sha256 EXACT_FROZEN_SHA256

## Unified test sequence

A. GitHub CI, now: Python 3.11 and 3.12 tests, Node syntax, native Godot smoke, synthetic two-scene queue/QA, mock FFmpeg handoff, tamper tests, Pi/Mac wrong and correct SHA, analytics cohort and owner adoption. Keep PR draft and unmerged.

B. Only later, after owner authorizes use of actual Mac/Pi: freeze commit, verify isolated SQLite backup and restore, confirm clocks and safe TLS, qualify actual installed Chatterbox/LTX/FFmpeg and rights. Produce ONE original two-scene Bunny red-ball pilot; listen to WAV, check LTX output and per-scene audio evidence, inspect every scene, build M13/M14 montage, use M16 Pi digest gate, render full master and run M7 technical + eleven human artistic/educational/rights criteria. Save private immutable archive and verify independent backup. Manual PRIVATE YouTube preview only after separate approval; public release requires a subsequent decision. Once publicly available and meaningful seven-day data exists, inspect first real M15 trends.

Stop and record an issue on any mismatched hash, failed quality criterion, unexpected network/model download/payment, unlicensed voice/art/music, inaccurate lesson, failed backup, lost worker lease, or unauthorized upload attempt.

## Remaining known limitations

CI uses synthetic media and analytics. Real Mac-installed MLX engines are not proven. Current M15 intake is manual validated JSON, not live OAuth access. Comparisons are associations that can be confounded by title, distribution, seasonality and audience. Independent media backup restore and legacy standalone Control Center v1-v3 migration have not been completed. Child-directed platform compliance and legal rights require real verification before publication.
