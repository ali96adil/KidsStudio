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
