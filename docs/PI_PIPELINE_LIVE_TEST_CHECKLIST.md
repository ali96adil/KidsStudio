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
