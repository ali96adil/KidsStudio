# Mac -> Pi -> YouTube: first live acceptance test

Do not enable unattended production until every step is confirmed.

1. On the Pi, install the code and Python environment. Use a dedicated
   unprivileged user. Provision private state, staging, inbox and session
   directories with owner-only permissions.
2. Configure a dedicated SSH key for Mac -> Pi file transfer. Verify
   the target directory is fixed and writable only by the intended user.
3. Create OAuth credentials outside GitHub (0600) with YouTube upload
   and video-read scopes; verify the expected channel ID.
4. Configure a private, owner-controlled episode title mapping (0600).
5. Run `inspect_pi_pipeline` and require `ready=true`. This is a
   **configuration-only** check; it does not contact YouTube.
6. Render one short original MP4 on the Mac. Transfer the MP4 and
   SHA-256 manifest over SSH. Deliberately transfer a truncated file
   first and verify the watcher does not enqueue it.
7. Transfer the complete file. Run the pipeline once. Confirm one
   queue job, one resumable session and a private YouTube upload.
8. Independently inspect the YouTube video and confirm the expected
   channel, privacy=private and matching local upload ledger entry.
9. Interrupt an upload and restart the Pi worker; verify that the
   server-side offset is queried before resuming and no duplicate
   video is created.
10. Confirm that no code changes privacy to public. Review the video
    manually on iPhone before considering any future release.

**Known limitations:** production retry policies and expired sessions
still need live validation; no Mac/Pi hardware or YouTube account is
accessible in this CI environment. A successful CI run is not evidence
of a real upload.

## Automated local checks before hardware acceptance

Run these commands from the repository root, in the Python environment used
for Kids Studio:

```bash
python -m unittest discover -s tests -p 'test_pi_*.py'
python -m kidsstudio.pi_offline_trial
python -m kidsstudio.pi_live_readiness \\
  --state-dir /path/to/private-upload \\
  --credentials /path/to/private/youtube.json \\
  --titles-file /path/to/private/titles.json
```

The offline trial uses temporary fake credentials and mocks the processing
tick. It **never** tests real network transfer or a YouTube upload.
The readiness command is read-only and reports `network_checked=false`,
`youtube_upload_tested=false`, and `public_release_enabled=false`.
It requires an initialized local queue and private media directories.

**Missing session safety:** if a queue job refers to a missing resumable
session, the worker marks the job failed and does not request OAuth or
create another upload. Reconcile the channel's private videos and local
binding ledger manually before considering any retry. Do not create a
fresh session merely to make the warning disappear: a previous upload
may have completed remotely.

Record the result of each real hardware step (Mac hostname, Pi service
status, video ID stored privately, channel privacy verified, and owner
review decision) in a private operator log, **not** in the repository.
Never commit OAuth credentials, resumable session URLs, or local media.

## One-command offline acceptance evidence

Run `python -m kidsstudio.pi_acceptance_report --out pi-acceptance.json`.
The report is a new JSON file and refuses to overwrite an existing file.
A passing offline report only proves first-boot and empty-pipeline checks;
its `evidence` explicitly leaves Mac-to-Pi transfer, real YouTube upload,
and owner review **untested**. Keep the report private if adding local
operational details later. The real acceptance procedure above is still
required before production is enabled.

## Ambiguous YouTube session creation: operator reconciliation

A durable `.session-intents/*.intent` marker is written **before** a
resumable-session request is sent. A network timeout cannot prove whether
YouTube created the session. The Pi watcher therefore refuses to create
another session or request OAuth for that episode/channel when a marker
exists without a queued job. Do **not** delete the marker to force retry.

Generate a private read-only report on the Pi (replace the state directory):

```bash
python3 -m kidsstudio.pi_session_reconciliation \\
  --state-dir /path/to/private-upload \\
  --out /path/to/private/reconciliation-001.json
```

The report has no YouTube access, does not verify remote videos, and does
not expose session URLs, tokens or local media paths. Inspect the actual
YouTube Studio account and channel, the local private upload binding ledger,
and any saved resumable session before choosing a manual recovery action.
Never infer that an absent local file means the remote video is absent.

Run `python3 -m kidsstudio.pi_live_readiness` again after review. Its
`no_ambiguous_session_intents` check is false when an unresolved or invalid
marker exists. It does not remove markers or authorize publishing. Keep
operator decisions and video IDs in a private record outside the repository.

**Hardware acceptance remains pending:** CI cannot verify SSH transfer,
YouTube OAuth, remote private visibility, real interruption recovery or
owner iPhone review. Never enable unattended public release.
