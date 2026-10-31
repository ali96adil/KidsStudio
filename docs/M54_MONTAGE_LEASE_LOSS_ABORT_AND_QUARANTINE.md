# M54 — Montage heartbeat validation, subprocess abort and no blind rerender

**Scope:** Kids Studio draft PR #28, source/CI only. No physical Pi/Mac,
owner media, live ComfyUI/LTX, YouTube token, upload or public release.

## Threat fixed

M53 rechecked a queued `episode_assemble` job immediately before Mac
execution, but the heartbeat only renewed its lease and an unavailable Pi
was merely recorded. FFmpeg (or face-cleanup subprocesses) could continue
running after the Mac lost its lease; results were not acknowledged, yet
hours of compute might be wasted and uncertain private intermediate files
could be mistaken for a new valid render.

## Changes

- **Pi:** every `episode_assemble` heartbeat rechecks the active studio,
  complete current M32 scene/recipe lineage and M49 frozen catalogue and
  scene set (as applicable) **inside a SQLite write transaction**. A
  mismatch revokes the lease, marks FAILED with
  `M54_MONTAGE_LEASE_REVOKED` and writes
  `M54_MONTAGE_HEARTBEAT_REVOKED` with a bounded reason. The authenticated
  coordinator denies that heartbeat instead of replying `ok: true`.
- **Mac:** while actively rendering a montage, send a heartbeat every
  10 seconds by default (not 45). Unacknowledged heartbeats, lease
  rejection or TLS/network loss set an in-process abort event. Never
  write the Mac journal's DONE record or acknowledge a result after
  this event.
- **Local FFmpeg/face subprocess:** the Mac's real `MediaExecutor`
  passes the abort event to the offline `EpisodeAssembler`, and its
  monitored subprocess runner watches the event at most every 250 ms.
  On abort it terminates the process (and on POSIX its process group),
  waits briefly, then force-kills if necessary. This is **local process
  termination, not remote arbitrary execution**. The subprocess's
  stderr is collected in a temporary file rather than an unbounded pipe.
  Existing unmonitored standalone assembler calls remain compatible.
- **Quarantine:** the already-created private per-job directory and
  `qa_report.json` remain on disk with
  `FAILED_REQUIRES_MANUAL_RECONCILIATION`; partially written MP4 files
  are not automatically deleted or promoted. The durable Mac
  `MediaJournal` retains STARTED on any failed/uncertain actuation.
  The same job ID cannot begin again automatically.
- **Job IDs:** the offline assembly run ID now accepts the real
  `[0-9a-f]{32}` queue ID form, even when it starts with a digit, as
  well as earlier safe explicitly named runs.

## Synthetic regression tests

1. An M32 montage loses its M49 binding after lease: next heartbeat
   revokes the job and records the exact reason.
2. Queue pause after lease revokes the next montage heartbeat.
3. A fake long Mac executor loses its lease during rendering: its result
   is never acknowledged, the Pi job fails, and the Mac journal stays STARTED.
4. A live synthetic Python subprocess is terminated after the abort event;
   previously written private output remains available for inspection.
5. A synthetic one-scene assembler abort produces a FAILED report and
   preserves an intermediate MP4, while the same run ID cannot be replayed.

## Important limitations

- The **actual** FFmpeg/face subprocess can be interrupted; injected
  test executors are only fenced at receipt time. A subprocess blocked
  in a short separate preflight/probe call can react after it returns.
- A process killed by a power outage/crash cannot run its final cleanup.
  The pre-existing STARTED journal/partial directory prevents blind retry.
- The heartbeat interval and HTTP timeout impose a finite detection
  delay; it is not a cryptographic real-time lock. A malicious worker
  with direct SQLite access is outside this design's trust boundary.
- Recovery of partial media and manual reconciliation require a
  subsequent controlled owner-authorized procedure; do not auto-resume
  the same final episode from the partial output.
- Software unit/CI success is not a real Mac/Pi qualification.
  All YouTube preview, rights/quality/child-safety and publication gates
  remain PRIVATE-only and unqualified until owner testing.

Keep PR #28 **DRAFT and unmerged**.
