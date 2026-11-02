# Pi staging watcher

`kidsstudio.pi_staging_watcher.scan_once` scans a trusted local
staging directory for JSON manifests sent by the Mac. Each manifest
must identify a single MP4 filename, episode ID, file size and SHA-256.

The watcher skips missing, partially transferred or invalid files. A
complete file is copied into the verified inbox and prepared as a
private YouTube resumable upload job. A saved session prevents normal
duplicate submissions on repeated scans.

Call `scan_once` periodically from a trusted Pi scheduler with a
`token_provider` and a trusted `title_for_episode` lookup. The title
must come from the approved production metadata, not arbitrary
incoming manifest text.

**Not yet deployed:** the existing systemd worker handles queued upload
recovery; it does not invoke this watcher. A production scheduler must
invoke it and manage retries of transient session-creation failures.
The current scan suppresses malformed or incomplete manifests and
duplicate-session errors; operators should inspect staging state.

Use dedicated SSH credentials and restricted staging directory
permissions. No automatic public publishing is implemented.
