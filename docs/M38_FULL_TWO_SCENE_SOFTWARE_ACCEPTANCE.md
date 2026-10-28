# M38 — Complete two-scene PRIVATE-only CI qualification

**Development branch only.** M38 is an end-to-end *software/evidence binding*
regression: real Linux FFmpeg/FFprobe media, fake AI adapters, disposable Pi
SQLite, no real Mac or Raspberry Pi deployment, no Google/YouTube OAuth.

## Actual end-to-end assertion

`tests/test_full_two_scene_private_cycle_m38.py` runs in the normal
Python 3.11/3.12 CI test matrix. It:

1. Initializes a series and frozen episode/scene/orchestrator plans. A dry
   run writes nothing; a paused queue will not enqueue.
2. Queues the **first voice** through M33 and verifies its exact current
   queue lease and completed WAV SHA. M34 decodes the real WAV with FFmpeg,
   while fake Whisper and two mock audio executables return pinned fake
   checks. M35 imports M23/M28 into Pi, approving only the scene voice.
3. Queues first LTX, checks a completed real sound-bearing MP4 SHA, recomputes
   M10 from *both* actual audio tracks, captures real FFmpeg frames, runs two
   **mock** AV adapters under M37, verifies model lineage and M28 signatures,
   then imports to accept only the current LTX job.
4. Repeats voice+LTX for the **second scene**, with distinct visual MP4 bytes,
   separate source rights receipts and M10 receipts. No new job is queued
   while the prior one is unreviewed.
5. Queues the final assembly only after all 4 scene stages are QA_APPROVED.
   Deliberately tampers with the second clip and proves M4 preflight blocks
   assembly **before output is created**, restores only this synthetic test
   fixture, then performs actual FFmpeg normalization/concatenation into one
   1280x720, H.264/AAC, 24-fps MP4. Source clip SHAs remain untouched.
6. Completes the exact Pi final render job, reconciles M33, conducts actual
   M7 full-decode integrity checks, stores and imports the current technical
   report. This must still block until separate final AI reviews exist.
7. Supplies two intentionally **mocked** final M27 independent reviewer
   receipts, referencing the actual final master SHA, actual sampled frames,
   technical report and a **synthetic** source-rights catalogue. The M27
   evidence ledger records only private internal readiness. M33 then marks
   the episode internally ready for its subsequent **separate** private
   upload policy and the owner's post-PRIVATE video review.

The checks assert **zero automatic PUBLIC authorizations, zero actual upload
actions, zero M31 repairs** and correct five queued job transitions. M34/M37
per-scene model verdicts are synthetic PASS values, NOT model qualification,
children's safety assessment, source-rights legal verification, actual
language intelligibility or lip-sync assurance. M27 final model verdicts are
also explicitly fabricated fixtures. A passing M38 CI alone must never enable
real production, even private upload, or imply the human has reviewed a
video. No final public publishing action belongs to this workflow.

## Hardware pilot exit criteria

Before one actual pilot on the owner's Mac and Raspberry Pi, independently
qualify the local speech/AV perception models on adversarial real clips;
verify rights provenance; establish authenticated Pi-to-Mac receipt transfer,
actual voice and image GPU renderers, a permanent secure model-signing-key
strategy, FFmpeg version/performance, YouTube PRIVATE-only OAuth plus owner
accept/accept-with-notes/request-changes after upload.

The existing PR #28 stays DRAFT and unmerged until those gates are passed.
