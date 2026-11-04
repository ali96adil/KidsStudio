# M15–M16 — Learning from real video performance + Pi/Mac freeze binding

## Status

Development on draft PR #28. NO software installed on owner Mac/Pi.
NO real Chatterbox or LTX GPU inference or finished episode has been tested.
NO YouTube credentials connected, API call, background monitor, paid AI,
video upload or public posting happened in this development turn.

## What connects to what

Approved original scripts -> M13 independent voice/LTX QA for each scene ->
M14 frozen M4 montage recipe -> M16 coordinator-pinned EXACT Mac catalogue
SHA256 -> Mac worker revalidates every original scene file -> M7 whole-episode
technical/educational/artistic/rights QA -> private owner archive and backup ->
later human-private YouTube preview -> owner-authorized publication ->
owner-verified YouTube performance export -> M15 trend proposals ->
owner ADOPT or REJECT -> at most one adopted experimental idea is included in
the next UNAPPROVED script-draft prompt -> two independent editorial reviews ->
owner approval. No past published episode is automatically rewritten.

## M16 — Pi knows the exact Mac catalogue

An episode with an M13 multi-scene plan can only queue an episode_assemble job
when the operator supplies the exact 64-character SHA256 from the frozen
M14 catalogue. It is retained in the immutable Pi queue payload and
transported through the authenticated coordinator.

The Mac media worker verifies three things BEFORE starting rendering:
- The Pi's approved SHA equals the locally loaded catalogue's bytes.
- The recipe has an M14 scene-evidence input if and only if this is a
  Pi-stamped multi-scene render.
- The original scripts, real WAV/MP4 scene outputs and receipts still match
  the sealed owner-approved scene plan and M4 montage recipe.

The worker rehashes its catalogue at each resolve to catch later file
replacement. Missing or wrong hashes cause CONFIG_REJECTED, not a render.
The owner still controls which approved catalogue SHA enters the Pi job.

Future operator action ONLY after real files, human QA and M14 freeze:

    python -m kidsstudio.series_cli --db /PRIVATE/studio.sqlite \
       queue-render colors-ar 1 --media-kind episode_assemble \
       --recipe colors_ar_ep01_v1 \
       --catalogue-sha256 EXACT_SHA_OF_FROZEN_CATALOGUE

## M15 — video performance learning agent

The first implementation is an offline, bounded, FREE observational analyzer.
It uses deliberately imported owner-verified data, not scraping, not arbitrary
untrusted API responses. Actual YouTube Analytics OAuth/data fetching is NOT
connected yet, so it will have NO real data until the channel has published
videos and the owner supplies genuine exported measurements.

The import must be a private absolute JSON file outside Git:

    {
      "schema_version":1,
      "source":"OWNER_VERIFIED_YOUTUBE_STUDIO_EXPORT",
      "profiles":[{
        "series_id":"colors-ar",
        "ordinal":1,
        "video_id":"EXACT11CHAR",
        "language":"ar",
        "format_type":"long",
        "duration_seconds":105,
        "published_date":"2026-11-02",
        "hook_style":"question_first",
        "story_style":"original_adventure",
        "pace_style":"calm",
        "participation_style":"ask_and_pause",
        "owner_education_verified":true
      }],
      "metrics":[{
        "series_id":"colors-ar",
        "ordinal":1,
        "video_id":"EXACT11CHAR",
        "snapshot_date":"2026-11-09",
        "window_days":7,
        "views":650,
        "impressions":6000,
        "ctr_percent":7.0,
        "average_view_percentage":75.0,
        "average_view_duration_seconds":78.75,
        "estimated_watch_minutes":850.0
      }]
    }

The example above is a FORMAT illustration only, not actual channel data
or a claim that a video was published. Each import needs real matching
video IDs/owner metadata and a real seven-day reporting window. The two
optional rate metrics may be null when genuinely unavailable, but unknown
metrics must never be fabricated. At least one profile and metric is required.

The analytical agent compares only videos in the same series, language,
format type (Shorts versus regular), and publication-age bucket. Minimum
3 videos per candidate and comparator, 300 views and 2,000 impressions
PER SIDE; observed median retention must exceed by at least 8 percentage
points AND view rate by at least 15%. Missing/small data means NO proposal.
These are conservative heuristic thresholds, not statistical causal proof.

All original import records are immutable (SHA-pinned source), no silent
replacement. On import, a single bounded analysis runs immediately and
stores PROPOSED observations in canonical Studio Brain SQLite. The dashboard
displays observation count, pending proposals and experiments the owner chose.

Explicit owner decisions are ADOPT_FOR_FUTURE_EXPERIMENT or REJECT, with a
substantive note. An adopted idea can modify only the next draft's OPTIONAL
creative brief, never an existing approved script, camera assets, safety
criteria, educational objective, or YouTube metadata. Independent editorial
and human final QA remain mandatory. No auto-clone/template/viral clickbait.

Later operator commands (after explicit install approval):

    studio-learning --db /PRIVATE/studio.sqlite init
    studio-learning --db /PRIVATE/studio.sqlite import \
      --file /PRIVATE/KidsStudio/analytics/verified.json
    studio-learning --db /PRIVATE/studio.sqlite status --series colors-ar
    studio-learning --db /PRIVATE/studio.sqlite decide \
      --proposal-id EXACT32CHARID \
      --decision ADOPT_FOR_FUTURE_EXPERIMENT \
      --owner-note "Preserve original lessons and validate a distinct new hook."

The input is owner-normalized JSON. Native YouTube Analytics API OAuth sync,
robust parsing of different Studio CSV exports and automated nightly sync
remain future work; do not suggest they are currently connected.

## Testing sequence

1. GitHub Actions CI for Python 3.11 and 3.12, JavaScript syntax and Godot
   smoke uses synthetic private stage receipts, two scenes, fake media and
   fake YouTube performance numbers. This can run NOW and needs no Mac.
2. On real Mac later: inspect model weights, license manifests and engine
   wrappers; do a read-only Mac contract check, never unattended downloads.
3. One real two-scene RED COLOR test: approved script, Bunny image import,
   exact scene WAV, owner voice QA, LTX output/continuity, owner animation QA.
4. Freeze M14 source catalogue; queue on Pi using EXACT M16 catalogue SHA.
   Produce real FFmpeg master, inspect all scenes, review M7 criteria.
5. Archive, independently back up and restore, owner preview only. No public
   YouTube release without separate explicit approval.
6. Only AFTER publishing original real videos (when owner authorizes it),
   import verified analytics and test M15 on real comparable data.

## Metrics and safety

Use YouTube Analytics/Studio definitions for impressions, thumbnail CTR,
views, estimated watch minutes, average view duration and average view
percentage. Analytics metric availability can vary by format/traffic source.
Performance associations are not causation. Focus on teaching outcomes,
original stories, clarity, voice/lip-sync quality and age suitability;
do not chase views with repetitive, auto-generated or deceptive kid videos.

Important current limits:
- No live Apple Silicon MLX wrappers or GPU inference qualified.
- No channel analytics imported yet; sample data are synthetic.
- No outside backup disaster recovery demonstrated.
- Legacy standalone Control Center v1-v3 DB remains unmigrated.
- Draft PR #28 is unmerged. Main stays untouched.
