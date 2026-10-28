# M24 — Review after the video is uploaded as PRIVATE

This is the owner-requested **post-upload review and feedback** workflow.
Production agents can finish the episode; once a future, separately
authorized YouTube integration uploads the final master as **PRIVATE**,
the owner can watch it and leave timestamped comments, accept it outright,
accept it with notes, or request a new version. A video saved as an
unpublished YouTube draft is not the same thing as an already-uploaded
PRIVATE watchable video. M24 starts only **after** an actual PRIVATE
upload. For now the upload is externally performed and recorded by
its 11-character YouTube ID; **no YouTube API is connected**.

**The M24 implementation has NOT been installed on the owner's Pi or Mac
and has NOT contacted YouTube.** GitHub CI uses fake IDs and SQLite.

## Workflow

1. AI agents prepare the final cut and run technical/editorial QA, with
   explicit independent approvals required by existing gates. No claim
   that the current repo already runs a complete autonomous upload.
2. The real owner-authorized uploader **in a future phase**, or owner
   manually, uploads the exact approved master as **PRIVATE** and records
   the resulting video ID + render job ID + master SHA256.
3. The recording is `PRIVATE_AWAITING_OWNER_REVIEW`. Privacy is **owner
   reported and not independently verified by YouTube API**. It does not
   change the platform's visibility.
4. In the local protected Owner Review UI, watch through the canonical
   YouTube URL, and add any number of immutable comments categorized
   by audio/animation/text/education/timing/visual/thumbnail/other and
   with optional timecode (e.g. 00:42). Comments remain linked to the
   **exact video ID + exact render job/master SHA**.
5. The owner chooses one final decision:
   - **APPROVE**: accepted with no required changes. Pre-existing
     timecoded notes, if any, are kept for future episode improvements.
   - **APPROVE_WITH_NOTES**: accepted for an eventual publication step,
     while supplied observations are retained as lessons for the agents.
     This is not a request to regenerate the approved current video.
   - **REQUEST_CHANGES**: not accepted; leave YouTube video PRIVATE.
     Record reason and timecodes; agents receive structured
     `TRIAGE_REVISION` feedback for planning a replacement. Creating
     a fresh render and a new PRIVATE video remains a **separate**
     operation and cannot be silently triggered here.
6. A rejected private video cannot become approved by a later button
   press. Only a **different finished master render with a different
   SHA256/job and new YouTube video ID** qualifies as version 2.
   Old notes remain preserved and attached to version 1.

Approval is per version. No approval carries forward. Critically,
**the UI and ledger never call YouTube publishing endpoints**.
Approval means the owner's review was recorded, not that the video is
public or even that YouTube's privacy was independently checked.
A future uploader must enforce a new, explicit publish transition
and current video/owner decision checks before switching PRIVATE to
PUBLIC or scheduling. Until that exists, publication remains manual.

## Separate owner-only review interface

The production status dashboard remains read-only on port 8793.
An explicit and separate HTTP UI on **loopback port 8794** accepts
write actions using an owner bearer token. Its key controls:

- Session token entered manually, held in page memory only.
- A dropdown of currently approved master receipts and exact SHA256;
  after a real PRIVATE upload, record its YouTube ID.
- List of pending/rejected/accepted private videos and open watch links.
- Comments with category, second offset and detailed text.
- Accept, accept-with-notes and request-changes, with visible confirmation.
- Review states shown read-only on the existing production dashboard.

It is deliberately not an internet-facing service; bind is
`127.0.0.1` only. Owner token is read only from environment, 32+
characters; POST requires exact Origin, correct Host, explicit action
header, exact JSON fields and strict request sizes. No passwords/owner
tokens in GitHub or URL parameters. Production deployment should use
a trusted private VPN or approved encrypted remote UI if accessing
from a separate iPhone; do **not** port-forward this loopback UI to
the public internet.

### Owner-device commands for future use, NOT run in GitHub CI

First initialize on the existing private Pi Studio Brain:

```sh
studio-preview-review --db /PRIVATE/pi-brain.sqlite init
```

For local owner-only UI, set a private environment variable
`KIDS_STUDIO_OWNER_REVIEW_TOKEN` with 32+ random characters,
then start:

```sh
studio-owner-review --db /PRIVATE/pi-brain.sqlite --port 8794
```

Open `http://127.0.0.1:8794/` on the **same host**, enter
the owner token. The UI does **not** request YouTube OAuth and
cannot itself upload or publish.

CLI equivalents (for an actual uploaded PRIVATE video only):

```sh
studio-preview-review --db /PRIVATE/pi-brain.sqlite \
  record-private colors-ar 1 --video-id EXACT_11_ID \
  --render-job-id EXACT_RENDER_JOB_ID \
  --master-sha256 EXACT_APPROVED_MASTER_SHA256

studio-preview-review --db /PRIVATE/pi-brain.sqlite \
  comment EXACT_11_ID --second 42 --category audio \
  --text "At 00:42 the blue color name is unclear"

studio-preview-review --db /PRIVATE/pi-brain.sqlite \
  decide EXACT_11_ID --decision APPROVE_WITH_NOTES \
  --note "Approved; next video needs a gentler narration pace"
```

For rejecting instead, the last command uses
`--decision REQUEST_CHANGES --note "..." `. No public video is
created from these commands. They never run a renderer or an AI model.

## Guarantees / remaining work

- Durable append-only comment/decision rows, at most one decision per
  private version, full historical rejection trail, and a current
  status summary in the read-only dashboard.
- Only owner-controlled local token endpoint or owner CLI can submit
  decisions; AI agents consume the notes but cannot self-approve.
- All private upload registrations require a current
  `EPISODE_APPROVED` master, completed matching render receipt and
  current M7 QA when that table exists. This does not independently
  prove that the exact master was uploaded or its platform privacy.
- Owner comment and decision actions revalidate the current master
  before updating. No stale approvals on replaced final renders.
- Comments attached to accepted versions are tagged for future
  experimentation; rejected versions are tagged `TRIAGE_REVISION`.
  This creates durable feedback for an agent, NOT an autonomous
  correction job or a claim that an agent has processed it.
- No YouTube connection/visibility verifier, no automatic PRIVATE
  upload, no PUBLIC/scheduled uploader, no remote phone-safe review
  access and no runtime qualification of owner hardware yet.

**Upcoming work**: authenticated YouTube upload integration with
exact master SHA & PRIVATE visibility attestation, AI-first internal
QA instead of unnecessarily stopping for human scene-level reviews,
and a separate owner-approved PUBLIC scheduling/publish handoff.
