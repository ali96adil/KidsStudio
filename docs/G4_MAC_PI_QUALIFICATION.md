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
