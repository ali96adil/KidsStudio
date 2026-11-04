# M68 Shorts — release gate (2026-10-31)

## Implemented
- Derived-short plan, vertical rendering, media decode/hash checks.
- Separate Shorts registry, six-axis review receipts, Pi staging checks.
- Shared M26 daily quota reservations and one-shot attempt journal.
- PRIVATE-only YouTube transport, upload-response ID pinning and authenticated privacy verification.
- Atomic review/policy revalidation when recording upload attempt.

## Production blockers
1. Source provenance is now bound through the M68 source binding and rechecked against M26 approved master receipts; this still needs validation with real production episode data.
2. Pi deployment: OAuth storage/refresh, transfer permissions, service launch and dashboard controls need end-to-end validation.
3. Quota lifecycle: unknown upload outcomes require operator reconciliation; do not expire attempted reservations automatically.
4. Review execution: six-axis results are persisted, but autonomous AI reviewer execution is not yet integrated.
5. Real upload: CI and Godot smoke do not verify an actual YouTube upload from Pi.

## Acceptance before unattended operation
- Provenance pinned to approved episode, source master SHA and series.
- Pi staging and local SHA verified from a trusted catalogue.
- Concurrent quota tests and crash/timeout reconciliation without duplicate uploads.
- One controlled real PRIVATE Pi upload verifies video ID, channel, privacy and processing.
- Owner can accept/reject/comment on private draft; PUBLIC always requires separate explicit approval.
- CI green on the final commit.

**Release decision: BLOCKED. Do not enable unattended Pi uploads or automatic public publication.**

## Operator preflight (read-only)

Before any one-shot upload, call `kidsstudio.m68_pi_preflight.assess(queue, short_id=..., series_id=..., media_path=Path(...))` on the Pi. A result of `READY_FOR_EXPLICIT_PRIVATE_UPLOAD` is only a diagnostic, **not permission to publish or to skip the owner policy**. Every blocking reason must be resolved before explicit invocation. The uploader rechecks the critical policy and QA in its own transaction.

Never place OAuth tokens in Git, episode metadata, upload receipts or UI logs. Provide a fresh token at invocation and do not log it. Do not schedule retries for `STARTED_UNCERTAIN` or `MANUAL_RECONCILIATION`. Reconcile unknown uploads in YouTube Studio before any new upload.

## Recent engineering updates

- M26 `_approved` source render receipt and 11-axis quality gate are checked when binding and before attempting a Short upload.
- A new read-only Pi preflight reports actionable blockers without Google network calls.
- A unique partial index prevents the same YouTube video ID being recorded for two Shorts.
- Test coverage includes forged source receipt, changed media, revoked source and duplicate attempts.

This is a **code-complete candidate for local integration testing only**, not a certified unattended production pipeline. The actual Pi environment, credentials, agent review implementation and one controlled real PRIVATE upload remain outstanding.

## Consolidated Pi operations inspection

Run on the Pi with the existing initialized SQLite database:

```sh
python3 -m kidsstudio.m68_pi_operations --db /absolute/path/to/studio.sqlite
```

This produces a JSON summary of staged/registered Shorts, review decisions,
quota reservation state, uncertain attempts, manual reconciliation and verified
PRIVATE uploads. It does **not** call Google, initialize missing tables, retry
uploads, or grant upload/public permission. Treat any STARTED_UNCERTAIN attempt
as potentially uploaded; reconcile it manually using the YouTube channel before
taking further action. No tokens are read or printed.

The M68 AI callback adapter is a contract for externally executed model
observations, **not a model runtime**. Six text evidence strings alone do not
prove that the video and audio were genuinely examined. Production release
remains blocked until a qualified local visual/audio reviewer is connected and
tested against actual media, plus one controlled Pi PRIVATE upload and owner
review in YouTube Studio.

## Mac and Pi pilot prerequisite commands (read-only)

On the Mac, from the project checkout:

```sh
python3 -m kidsstudio.m68_runtime_prerequisites --role mac --require-ollama
```

On the Pi, from the same checkout with its existing SQLite database and a
previously transferred private Short:

```sh
python3 -m kidsstudio.m68_runtime_prerequisites --role pi \
  --db /absolute/path/to/studio.sqlite \
  --media /absolute/path/to/staged-short.mp4
```

A result of `PREREQUISITES_PRESENT_NOT_END_TO_END_TESTED` means only
that named local executables and file paths exist. It does **not** prove
Ollama is running, models are loaded, actual AV content was reviewed, SSH
transfer worked, or YouTube OAuth/private upload succeeded. The diagnostics
perform no network calls or modifications. Next pilot steps require separate
operator-controlled real media tests and a single explicit PRIVATE upload.

## Local actual-frame Ollama pilot (Mac; no upload)

```sh
python3 -m kidsstudio.m68_local_vision_diagnostic \
  --root /absolute/private/short-bundle \
  --handoff /absolute/private/short-handoff.json \
  --mp4 /absolute/private/short.mp4 \
  --script /absolute/private/approved-script.txt \
  --ffmpeg "$(command -v ffmpeg)" \
  --ffprobe "$(command -v ffprobe)" \
  --model YOUR_INSTALLED_VISION_MODEL
```

Requires Ollama running at the explicit loopback endpoint and a model that
accepts real images. The diagnostic decodes actual MP4 frames, sends them
with the approved script to the local model, and records model observations.
It **always rejects** the audio, copyright, pedagogy and source-consistency\naxes: the existing child-visual-safety model checks cannot establish any of\nthese. Only visual safety and age appropriateness can be assessed. Its output must not be used as an all-axis PASS or
permission to upload. A separate qualified audio reviewer and verified
rights/provenance catalogue must be integrated before six-axis acceptance.
The command only prints a receipt; it does not write the Pi review database.

## Rights provenance inventory (read-only)

Before attempting independent legal review, create a private JSON manifest
with `schema_version: 1`, the pinned `video_sha256`, and a nonempty
`assets` list. Each asset requires a unique `id`, `kind` (image,
audio, music, font, video, voice or other), `rights_basis` (original,
licensed, public_domain or permission), human-readable `source`,
`evidence_reference`, absolute `path` and the actual file `sha256`.

```sh
python3 -m kidsstudio.m68_rights_inventory \
  --manifest /absolute/private/rights.json \
  --video-sha256 YOUR_PINNED_MP4_SHA256
```

The validator checks exact asset bytes and declared provenance completeness.
A documented inventory is **not** legal verification, and never grants
upload or publication permission. Rights review must be completed separately.

## Consolidated review diagnostic

```sh
python3 -m kidsstudio.m68_consolidated_review \
  --root /absolute/private/short-root \
  --handoff /absolute/private/handoff.json \
  --vision-receipt /absolute/private/vision.json \
  --rights-manifest /absolute/private/rights.json
```

This read-only command joins the SHA-pinned local vision diagnostic with
the asset rights inventory and reports missing pedagogy, audio, copyright,
and script-consistency evidence. It **always returns a blocked status and
exit code 2** until a separate independent six-axis review system is
implemented and qualified. It never stages or uploads media.

## Optional audio evidence diagnostic

The consolidated diagnostic accepts `--audio-receipt /absolute/private/audio.json`.
The receipt must bind `short_id`, `source_episode_id`, and `video_sha256`,
declare actual MP4 audio observation, include an audio SHA, two distinct
model hashes and bounded evidence. This is **a claim-format validator**,
not proof that those model runners executed: the current bridge does not
execute or attest them. Even a claimed PASS leaves the consolidated audio
axis blocked and cannot authorize YouTube upload. Qualification must use
the existing pinned local audio/AV runners with verifiable source receipts.
