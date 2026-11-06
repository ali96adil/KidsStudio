# G4 — supervised Mac / Raspberry Pi qualification checklist

**Scope:** operator-controlled, private-only qualification. This is NOT permission to start unattended generation, invoke paid APIs, upload to YouTube or publish.

## Before running

- Record Git commit, OS versions, Python version, device names and local clock offsets.
- Back up the existing SQLite queue and private artifact directory while workers are stopped. Do not overwrite a live database.
- Confirm private artifact root is outside the Git repository, has adequate free space, and is not web-served.
- Confirm no API keys, prompts, private child imagery, or generated scripts will be placed in CI logs.
- Keep automatic publishing disabled. Any YouTube upload remains a separate owner-authorized step with PRIVATE visibility.

## Qualification gates

| Gate | Evidence to capture | Failure action |
| --- | --- | --- |
| G4.1 Mac isolated worker | One explicitly requested local draft, source provider ID, immutable answer/manifest SHA256 | Stop worker; retain evidence privately |
| G4.2 Read-only editorial evaluation | Metadata-only JSON, trusted SHA from queue, exit code; no queue/event mutation | Reject artifact and investigate |
| G4.3 Independent reviewer | Different provider from draft; reviewer source SHA matches parent; review still unverified | Mark child failed; preserve parent |
| G4.4 Pause/restart | SQLite state and artifacts survive clean stop/restart; no duplicate review jobs | Keep paused; inspect queue events |
| G4.5 Pi transfer boundary | Compare sender/receiver SHA256, check TLS identity and private permissions; do not assume local SQLite is shared | Stop transfer; quarantine mismatched bytes |
| G4.6 Pi uploader dry run | Verify that no YouTube request or public visibility change is issued | Disable uploader and review logs |
| G4.7 Owner review | Human inspects educational accuracy, age suitability, audio/visual quality and rights before any release decision | Leave draft private |

## Evidence record template

- Commit:
- Date and local timezone:
- Mac and Pi versions:
- Gate ID:
- Input artifact SHA256:
- Output artifact SHA256:
- Queue state before/after:
- Provider identifiers (no credentials):
- Result: PASS / FAIL / NOT_RUN
- Redacted log path:
- Owner sign-off (if required):
- Follow-up issue:

**Stop conditions:** unexpected network traffic, any paid model invocation without approval, checksum mismatch, leaked private text, duplicate dispatch, auto-publish attempt, or unauthorized write. Stop and preserve private logs; do not silently retry.

## Rollback

Stop worker/coordinator processes, keep publishing disabled, restore the pre-test queue backup only after preserving a separate copy of current evidence, and return to the last known-good commit. Never delete generated private artifacts automatically. Re-running tests against the live queue is not authorized by this checklist.

**Current status:** NOT_RUN on physical Mac/Pi. GitHub synthetic CI and Godot smoke cannot substitute for these gates.

## Read-only preflight command

With the worker **stopped**, run locally on the host that actually holds the queue database:

```bash
python -m kidsstudio.g4_preflight \
  --artifact-root /private/kidsstudio/artifacts \
  --db /private/kidsstudio/state.sqlite
```

The command reads a SQLite immutable snapshot (no queue writes), checks the expected schema, basic integrity, private-root placement, available disk space (at least 1 GiB) and Python 3.11+. It prints a metadata-only JSON report, with exit 0 for preflight pass and 1 for blocked. **Do not point it at a concurrently changing database**: immutable read mode deliberately does not merge pending WAL updates, so a stopped worker and clean checkpoint are prerequisites for meaningful results. This is not an end-to-end readiness or security audit. A pass never enables publishing.

If Mac and Pi use different local databases, run separately for each actual local queue; this command does not test network transport.

## Read-only host preflight command

After installing the repository on each host, inspect existing private paths **without starting workers**:

```bash
python -m kidsstudio.host_preflight \
  --artifact-root /private/kidsstudio/artifacts \
  --queue-db /private/kidsstudio/state.sqlite \
  --minimum-free-gib 2
```

Exit code `0` means configured static checks passed; `1` means action required; `2` means invalid input or inspection error. This command does **not** open SQLite, validate database contents, invoke AI, check network TLS, or authorize production. Paths must already exist; the command does not create them. Optional Godot/FFmpeg presence is informational, not a readiness guarantee. Store the JSON report privately.

## Offline preflight command (read-only)

On each device, from an installed KidsStudio checkout, **only after creating the private directory yourself**:

```bash
python -m kidsstudio.host_readiness \
  --artifact-root "$HOME/kidsstudio-private/artifacts" \
  --db "$HOME/kidsstudio-private/state.sqlite" \
  --min-free-gib 2
```

Omit `--db` if this device does not own a local SQLite queue. The probe never opens the DB, creates directories, or contacts any host. It emits non-sensitive JSON with machine/OS/Python information and Boolean checks. Exit 0 = ready for *supervised tests only*; 1 = one or more checks failed; 2 = probe input/error. No production approval is implied.

The probe checks the artifact directory itself for POSIX private permissions; its parent directories, actual ownership, ACLs, encryption, TLS and remote transfer require separate manual inspection. A directory that does not exist is **NOT_READY**; the probe deliberately will not create it.

## G4.5 staged-file integrity verification (no transfer)

After an independently authorized private transfer, obtain the expected SHA256 from the Mac's trusted source record and run on the Pi's private staging directory:

```bash
python -m kidsstudio.transfer_verify \
  --root "$HOME/kidsstudio-private/incoming" \
  --relative-path "episode.mp4" \
  --expected-sha256 EXPECTED_MAC_SHA256
```

Exit `0` = staged bytes match, `1` = mismatch, `2` = invalid or unsafe input. The tool hashes the local staged file only, reading in 1 MiB chunks (maximum 20 GiB). It does **not** send files, prove transport security, authenticate the Mac, verify video decodability, or grant upload/publication approval. Confirm transport TLS/SSH identity and permissions separately. The trusted SHA must not be taken from an untrusted received manifest.

## Explicit Pi private inbox promotion (opt-in)

After trusted SSH/SFTP transport and a matching SHA256, an operator may explicitly promote the already staged file into a **pre-existing**, private (POSIX mode 0700) inbox:

```bash
python -m kidsstudio.inbox_promote \
  --source-root "$HOME/kidsstudio-private/incoming" \
  --relative-path episode.mp4 \
  --destination-root "$HOME/kidsstudio-private/ready" \
  --destination-name episode.mp4 \
  --expected-sha256 EXPECTED_TRUSTED_MAC_SHA256
```

This command is a local write, **not** an automatic step. It checks the source digest, streams a private temporary copy, rechecks the digest and uses an exclusive atomic hard-link to install the final name (existing names are never overwritten). Destination must exist, be private and outside Git. The command performs no network transfer, YouTube upload, queue mutation, or publication approval. Exit 0 = private promotion succeeded; 2 = rejected. It is not a replacement for SSH identity checks, private staging permissions, media inspection, or human review. Stop writers to the staging directory during promotion to avoid concurrent file changes.

## Offline PRIVATE upload handoff preflight (not a YouTube uploader)

```bash
python -m kidsstudio.private_upload_preflight \
  --inbox-root "$HOME/kidsstudio-private/ready" \
  --relative-path episode.mp4 \
  --expected-sha256 EXPECTED_TRUSTED_MAC_SHA256 \
  --owner-reviewed
```

The `--owner-reviewed` flag is an **operator assertion only**, not authenticated approval. Without it, the preflight holds the file private. The check verifies the SHA256 and nonempty .mp4 filename, but **does not** decode the video, establish content rights, authenticate the operator, invoke YouTube, or authorize upload/publication. Even a `READY_FOR_MANUAL_PRIVATE_UPLOAD` report requires a separate authorized upload step with visibility PRIVATE and independent media/rights checks. Never treat this flag as permission to publish.

## PRIVATE upload eligibility gate (offline only)

To evaluate a file in the private ready directory **without** contacting YouTube:

```bash
python -m kidsstudio.private_upload_gate \
  --private-root "$HOME/kidsstudio-private/ready" \
  --relative-path episode.mp4 \
  --expected-sha256 EXPECTED_TRUSTED_MAC_SHA256
```

Default result is BLOCKED even if the SHA matches. The optional `--authorize-private-upload` flag represents **explicit owner permission for a future, separate private-only upload**; it does not upload anything. The output remains `upload_submitted=false`, `publication_approved=false` and `required_youtube_visibility=private`. A separate uploader integration must enforce the actual YouTube API privacy setting and record the uploaded private video ID before owner review. Exit 0 means eligible for a later private-only upload, **not** uploaded or approved for public release; 1 blocked; 2 invalid input.

## Offline uploader handoff contract

The repository README describes Pi coordination and remote transport as prototypes; do not assume a production YouTube uploader exists. The following command emits only a metadata contract for a **separate future** uploader, with no paths or credentials in JSON:

```bash
python -m kidsstudio.private_handoff \
  --private-root "$HOME/kidsstudio-private/ready" \
  --relative-path episode.mp4 \
  --expected-sha256 EXPECTED_TRUSTED_MAC_SHA256 \
  --episode-id colors_ar_01 \
  --authorize-private-upload
```

Without the explicit flag the result is BLOCKED. Even when ready, the contract says `visibility=private`, `upload_submitted=false`, `publication_approved=false`, and `requires_owner_video_review=true`. This is **not** a YouTube upload or a credential/configuration workflow. No auto-publication is permitted.

## YouTube PRIVATE request preview (offline, no OAuth)

```bash
python -m kidsstudio.youtube_private_dry_run \
  --private-root "$HOME/kidsstudio-private/ready" \
  --relative-path episode.mp4 \
  --expected-sha256 EXPECTED_TRUSTED_MAC_SHA256 \
  --episode-id colors_ar_01 \
  --title "تعلم الألوان" \
  --language ar \
  --authorize-private-upload
```

This prints a proposed YouTube `snippet` and `status` payload with `privacyStatus=private` and `selfDeclaredMadeForKids=true`, **not** an API request. The owner must verify whether each video should be designated made-for-kids before any real upload. No SDK/OAuth, network, YouTube ID, or upload is involved. The real uploader is a separate, not-yet-qualified component and must enforce privacy on the server side. Titles and descriptions are included in CLI stdout: treat output as private editorial metadata.

## Read-only episode dashboard projection

`kidsstudio.episode_lifecycle.project_episode` takes a trusted list of explicit episode state events and computes a **display-only** lifecycle status. A CLI is available:

```bash
python -m kidsstudio.episode_lifecycle \
  --episode-id colors_ar_01 \
  --events-json /path/to/private/episode_events.json
```

The JSON file must contain a list such as `[{"episode_id":"colors_ar_01","state":"SCRIPT_READY"}]`. This is a **projection**, not a durable event log, producer, or integration with the current SQLite queue. It rejects skipped transitions, other episode IDs and claimed publication approval unless the supplied event explicitly identifies the owner. It does not authenticate that claim, approve anything in production, or publish a video. Real dashboard integration must use authenticated provenance from trusted persisted events, not untrusted JSON.

## Actual StudioQueue read-only dashboard counts

```bash
python -m kidsstudio.queue_dashboard \
  --db "$HOME/kidsstudio-private/state.sqlite"
```

This reads the **existing** local SQLite `jobs` and `settings` tables with `mode=ro` and `PRAGMA query_only=ON`. It outputs per-kind/per-state aggregate counts, total jobs and pause status, but **no** payloads, paths, job IDs, or secrets. It does not initialize a database, write queue state, claim a lease, or infer an episode's editorial/publication status. The separate `episode_lifecycle` projection remains unconnected until authenticated episode provenance is implemented. If the database is unavailable or schema differs, the command fails closed.

## Dashboard view model (read-only)

```bash
python -m kidsstudio.dashboard_summary \
  --db "$HOME/kidsstudio-private/state.sqlite"
```

This converts the actual queue aggregate snapshot into five counters: `waiting`, `running`, `completed`, `needs_attention` and `cancelled`, plus `queue_paused`. Counts are validated for consistency and never treated as editorial approvals. `episode_status_available=false` and `private_upload_status_available=false` explicitly indicate missing authenticated integration. It is a JSON view model, not a hosted dashboard/UI or a new queue.

## Local read-only web dashboard preview

On the same host as the local SQLite queue:

```bash
python -m kidsstudio.dashboard_web \
  --db "$HOME/kidsstudio-private/state.sqlite" \
  --port 8787
```

Open `http://127.0.0.1:8787/` on that same host. The service binds **only** to loopback, provides GET `/` and GET `/api/summary`, rejects POST and exposes no remote authentication or operator actions. Do **not** port-forward or bind it to LAN/WAN: this is an unauthenticated local development preview, not the eventual secured Pi dashboard. The page shows aggregate queue counters only; no individual episode states or owner review interface yet. Missing SQLite data returns HTTP 503. No production daemon is installed or started by these commits.

## Private owner review notes (isolated database)

Create a private directory outside Git first (`chmod 700`). Notes are stored in a separate local SQLite database, not in the production queue:

```bash
python -m kidsstudio.episode_notes --db "$HOME/kidsstudio-private/notes.sqlite" init
python -m kidsstudio.episode_notes --db "$HOME/kidsstudio-private/notes.sqlite" add \
  --episode-id colors_ar_01 --text "راجع مستوى الصوت"
python -m kidsstudio.episode_notes --db "$HOME/kidsstudio-private/notes.sqlite" list \
  --episode-id colors_ar_01
python -m kidsstudio.episode_notes --db "$HOME/kidsstudio-private/notes.sqlite" resolve \
  --episode-id colors_ar_01 --note-id 1
```

Notes are append-only: resolving adds a RESOLVE event and preserves the original text. There is **no delete or publication approval command**. This is an unauthenticated local operator CLI, not a remotely accessible review UI. Keep the database private and backed up; the future secured dashboard must authenticate the owner and never treat resolved notes as permission to publish.

## Optional local notes read endpoint

```bash
python -m kidsstudio.dashboard_web \
  --db "$HOME/kidsstudio-private/state.sqlite" \
  --notes-db "$HOME/kidsstudio-private/notes.sqlite" \
  --port 8787
```

GET `http://127.0.0.1:8787/api/notes?episode_id=colors_ar_01` returns notes from the **separate** local notes database. The endpoint is disabled unless `--notes-db` is supplied; POST is rejected. Notes can contain private editorial text, so keep this unauthenticated prototype bound to loopback only and do not port-forward. The HTML currently displays aggregate counters; the notes endpoint is a read-only integration seam for a future authenticated owner review interface, not a finished review UI.

## Read-only episode notes inside the Arabic dashboard

With `--notes-db` configured, the dashboard HTML now shows an episode-ID search form and displays notes with **pending/resolved** labels. Notes are rendered with DOM `textContent`, not `innerHTML`, so note content is not interpreted as markup. Without `--notes-db`, the section stays hidden. This UI is **read-only**, and its form only performs GET; note creation/resolution remain private CLI actions. Never expose this unauthenticated localhost preview to the network.

## SHA-bound video review receipt draft

A reviewer can produce an offline, metadata-only receipt for **exactly one** verified video byte sequence:

```bash
python -m kidsstudio.video_review_receipt \
  --episode-id colors_ar_01 \
  --video-root "$HOME/kidsstudio-private/ready" \
  --relative-path episode.mp4 \
  --expected-sha256 TRUSTED_SHA256 \
  --review-outcome REVISION_REQUIRED \
  --reviewer-notes "راجع صوت الأرنب"
```

The tool rehashes the local file and rejects changed content, unsafe paths, and unsupported outcomes. Outcomes are `NEEDS_REVIEW`, `REVISION_REQUIRED`, `ACCEPTED_PRIVATE`; **none** authorizes public release. The receipt is emitted to stdout, **not persisted**, and reviewer identity is **not authenticated**. This is not a YouTube approval or an actual video preview UI; those require separate secured implementation and owner testing.

## Private SHA-bound review history

A separate private SQLite database can retain successive video review receipts:

```bash
python -m kidsstudio.video_review_history --db "$HOME/kidsstudio-private/reviews.sqlite" init
python -m kidsstudio.video_review_history --db "$HOME/kidsstudio-private/reviews.sqlite" record \
  --episode-id colors_ar_01 --video-root "$HOME/kidsstudio-private/ready" \
  --relative-path episode.mp4 --expected-sha256 TRUSTED_SHA256 \
  --review-outcome REVISION_REQUIRED --reviewer-notes "راجع الصوت"
python -m kidsstudio.video_review_history --db "$HOME/kidsstudio-private/reviews.sqlite" list \
  --episode-id colors_ar_01
```

Each record rehashes the video and appends its SHA, size, outcome, and notes. Older records remain intact when a new video version is reviewed. There is no delete, modify, authenticated reviewer identity, owner publication approval, YouTube call, or dashboard integration yet. Run only on a trusted private host; review notes are sensitive and the SQLite file requires backup.
