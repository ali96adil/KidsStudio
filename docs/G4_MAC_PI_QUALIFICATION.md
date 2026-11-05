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
