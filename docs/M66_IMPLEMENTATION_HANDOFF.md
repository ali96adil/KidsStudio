# M66 implementation and qualification handoff

This milestone is **code-complete for the offline diagnostic harness**, not qualified on physical Mac/Pi or a real YouTube account.

## Added modules

- `python -m kidsstudio.m66_readonly_preflight --db /private/studio.db --inbox-root /private/inbox --journal /private/upload.sqlite` — read-only station checks.
- `python -m kidsstudio.m66_transfer_fault_lab --source /tmp/sample.mp4 --destination /tmp/inbox --interrupt-after 1048576` — offline synthetic partial transfer. Repeat without `--interrupt-after` to resume.
- `python -m kidsstudio.m66_upload_reconciliation --journal /private/upload.sqlite --job-id <32-hex-job>` — read-only ambiguous upload classification. Never starts Google upload.
- `python -m kidsstudio.m66_qualification_report --evidence /private/m66-evidence.json` — fail-closed assessment.
- `python -m kidsstudio.m66_status_export --evidence /private/m66-evidence.json --output /private/m66-status.json` — sanitized dashboard feed, not a hosted dashboard.

## CI / offline validation

Existing CI runs `python -m compileall -q kidsstudio tests` and `python -m unittest discover -s tests -v`. New tests cover station readiness, simulated resume, corrupted partial bytes, SHA mismatch, duplicate ready files, upload journal uncertainty, privacy qualification and sanitized reporting. CI completion must be verified separately; adding tests does not prove they pass.

## Real-device acceptance (owner-supervised)

1. Use throwaway non-sensitive media, with Mac rendering and Pi LAN receipt; record source and Pi SHA-256.
2. Interrupt SSH/rsync and resume; verify no `.ready` media until Pi hash matches.
3. Switch Mac off after receipt; verify Pi service continues, then reboot Pi.
4. Use Pi-only OAuth to upload one disposable video **PRIVATE**; independently verify owner channel, video ID and privacy via authenticated Google GET.
5. Inject an ambiguous Google POST/PUT interruption; do not issue a second videos.insert for that master. Require reconciliation.
6. Record owner review decision and time-coded feedback; never authorize PUBLIC from a diagnostic.
7. Save evidence privately and run the M66 qualification report. The evidence JSON is an assertion provided by the operator, **not cryptographic proof**; independent log inspection is still mandatory.

## Known limits

- The M66.2 lab is a local file simulation, not actual rsync.
- M66.4 classifies existing journal rows; it does not safely resume an ambiguous Google upload or prove it completed.
- M66.5 exports JSON; it is not yet connected to a live authenticated owner dashboard.
- Never put OAuth credentials, actual upload IDs, private evidence or media in Git.
- PR #28 must stay draft until hardware/Google acceptance and CI evidence.
