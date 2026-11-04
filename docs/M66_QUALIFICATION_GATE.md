# M66 — Mac → Pi acceptance qualification

## Verified CI evidence (2026-11-04)
Commit `7ff3974d6d1db9ab323dc6fcdfe51b09b548606d`:
- GitHub Actions CI run `41799481604`: completed, success.
- GitHub Actions Real Godot smoke run `41799481625`: completed, success.

These are **synthetic CI checks**, not proof of live owner Mac/Pi, SSH, YouTube, or Google OAuth.

## Offline test commands
From the repo root after installation:
```bash
python3 -m unittest discover -s tests -p 'test_m66_transfer_integrity.py' -v
python3 -m unittest discover -s tests -p 'test_m66_resume_simulation.py' -v
python3 -m kidsstudio.m66_transfer_integrity /private/source.mp4 /private/pi-received.mp4
```

The transfer-integrity CLI checks full SHA-256 and length, rejects symlinks, missing files and mismatches. The separate resume module is **local staging simulation only**: it writes a `.part`, verifies source prefix, resumes, verifies the complete result and atomically replaces a final file. It is **not** an SSH/rsync transfer implementation, is not hardened against hostile concurrent writers, and must not be wired into production without further review.

## Acceptance matrix

| Gate | Current status | Evidence required |
| --- | --- | --- |
| SHA-256 local verification | CI PASS | Synthetic tests |
| Local interruption and resume simulation | CI PASS | Synthetic tests |
| Real pinned-host SSH/rsync resume | BLOCKED | Owner Mac and Pi with synthetic media |
| Pi persistent inbox across reboot | BLOCKED | Reboot and filesystem receipts |
| Mac OFF while Pi continues | BLOCKED | Live Pi service logs, no Mac |
| Ambiguous Google resumable upload | BLOCKED | Fake transport crash tests and live opt-in qualification |
| No duplicate `videos.insert` | BLOCKED | Crash/restart journal and API evidence |
| Shared budget and owner review | BLOCKED | Policy integration and PRIVATE preview |
| PUBLIC publishing | DISABLED | No automatic activation |

## Live-device acceptance rules
1. Start with a synthetic MP4, never children's private footage.
2. Use pinned SSH host identity, dedicated restricted Pi inbox and an owner-approved service identity.
3. Force a mid-transfer interruption; verify partial file is not ingestible, then resume and compare SHA-256 on **both** machines.
4. Reboot Pi and power down Mac; ensure Pi-local approved media and journal persist.
5. For any uncertain Google upload state, **fail closed**: never blindly repeat `videos.insert`. Require verified reconciliation.
6. Verify that owner review happens only after a verified PRIVATE YouTube processing result. Public release remains disabled.
7. Keep timestamps, versions, pass/block reasons and redacted logs in a private local report; do not push OAuth tokens, child media, account IDs or local paths to GitHub.

PR #28 and PR #31 remain DRAFT/unmerged until live owner-device acceptance. See issue #30.
