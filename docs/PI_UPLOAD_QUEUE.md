# Persistent Pi private upload queue

`PiUploadQueue` stores pending, running, completed and failed recovery jobs
in SQLite. `claim()` uses an immediate transaction to avoid concurrent
claims; `recover_interrupted()` moves jobs left running after a crash
back to pending. `process_one()` runs one job via the OAuth-refreshing
supervisor and records success or a redacted failure.

**Important:** only enqueue sessions created by the trusted uploader.
The queue does not create initial upload sessions. A service manager must
call `recover_interrupted()` at startup and invoke the worker regularly.
Do not run two independent worker processes with startup recovery
simultaneously: a startup reset could requeue an active job.

Failed jobs remain failed for operator inspection; automatic unbounded
retry is intentionally disabled. Reboot recovery is unit-tested but not
yet verified on a physical Pi. No YouTube public visibility writes occur.
