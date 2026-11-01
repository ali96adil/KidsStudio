# Parallel CI triage and production qualification — 2026-11-01

## Verified starting point
- Base: optional-ai-media-providers head `979bf47c391c39339d573332fd8d97763d362615`.
- PR #28 and PR #29 remain draft. Neither is authorized for production.
- Current `.github/workflows/ci.yml` runs all unittest discovery in each Python matrix job; isolate failures before modifying tests.
- No physical Mac/Pi validation or YouTube upload is implied by a passing CI run.

## Parallel work lanes
A. CI diagnosis: collect failed job names, tracebacks, dependency versions, and the exact commit SHA. Reproduce first failing test independently; fix root causes, never suppress a failing test merely to turn CI green.
B. Art qualification: validate the real two-part bunny ComfyUI workflow and inspect visual evidence on owner Mac. No full-rig approval from synthetic tests.
C. Media integration: verify script -> scene voice -> scene QA -> montage provenance -> private preview. Keep all immutable source hashes and fail-closed gates.
D. Pi delivery: verify checksummed local transfer, crash recovery, and private YouTube upload only with owner credentials and explicit approval.
E. Owner dashboard: read-only overview first, then bounded review actions with audit records.

## CI execution policy
- Independent lanes can progress while CI runs.
- Never merge a failing required check or ship a private/public upload on unverified evidence.
- Pin each result to commit SHA; stale CI cannot approve a newer commit.
- Re-run targeted tests first; run full Python matrix and native Godot/FFmpeg integration before merge.
- Mark physical-device, account, licensing, and quality checks separately from synthetic CI.

## Definition of done
1. CI green at exact candidate SHA.
2. Real Mac character art and motion proof approved.
3. Full original episode rendered and independently reviewed.
4. Mac-to-Pi transfer verified by hashes and recoverable restart.
5. Private YouTube upload verified with owner review; no automatic public release.
6. Dashboard exposes job states, failed checks, agent assignments and owner notes.

## Next execution checkpoint
Record actual CI run URLs and failed steps, create separate commits for each independent lane, and do not promote PR #28/#29 until integration evidence is available.
