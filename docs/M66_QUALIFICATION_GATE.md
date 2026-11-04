# M66 — Mac → Pi acceptance qualification

This is an **offline-only** first slice of issue #30, not proof of a real Mac/Pi transfer, Google upload, or restart recovery.

## Offline smoke
Run from the repository root:
```bash
python3 -m unittest discover -s tests -p 'test_m66_transfer_integrity.py' -v
python3 -m kidsstudio.m66_transfer_integrity /private/source.mp4 /private/pi-received.mp4
```
The CLI verifies full SHA-256 and length, rejects symlinks, missing files and mismatches. It performs **no network or upload**. Never commit source media or credentials.

## Still BLOCKED for release
- Actual pinned-host SSH/rsync interrupted transfer and resume, with Pi-side verification
- Persistent Pi inbox and systemd restart/reboot while Mac is off
- Ambiguous Google resumable session recovery without duplicate insert
- Shared upload budget, revision/pause behavior and owner PRIVATE preview
- Actual owner-device evidence and explicit opt-in Google credentials

Keep PR #28 draft, PUBLIC publishing disabled. Record results in private redacted report.
