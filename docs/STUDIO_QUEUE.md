# Studio Brain v0.1 — durable, local-first production control plane

This is the first persistent coordinator for KidsStudio, intended eventually
for the always-on Raspberry Pi 4. It is deliberately **not** an autonomous
external-action agent or a web service yet.

## Responsibilities
- SQLite database on local Pi storage (WAL, private file permissions).
- Idempotent job creation with stable owner request key.
- Explicit allowlist of job types: character_generate, rig_review,
  godot_render, script_draft, editorial_review, archive_verify.
- Atomic single-worker claim within SQLite `BEGIN IMMEDIATE` transactions.
- Renewable leases and **fencing generation tokens** to reject stale
  results when a worker loses its lease or a job is cancelled.
- Bounded retries (1–3), backoff on transient failure, terminal failure
  for an exhausted expired lease, event audit journal.
- Pause/resume new dispatch; cancel pending or leased work without modifying
  finished assets. Only local owner/authorized operators should invoke it.
- No data/password/secret fields accepted in job payloads or result records.
- No shell execution, automatic model download, internet API requests,
  spending, social outreach, YouTube publishing or implicit schedules.

## CLI

Create a new DB on Pi-attached/local storage, **outside Git or network NAS**:

    studioctl --db /private/local/kidsstudio/studio.sqlite init

Enqueue a syntactically approved job without executing it:

    studioctl --db /private/local/kidsstudio/studio.sqlite enqueue \
      --kind character_generate \
      --key bunny-v02-rig-first-v1 \
      --payload-file /private/local/kidsstudio/requests/bunny.json

Inspect and control dispatch:

    studioctl --db /private/local/kidsstudio/studio.sqlite status
    studioctl --db /private/local/kidsstudio/studio.sqlite list
    studioctl --db /private/local/kidsstudio/studio.sqlite events
    studioctl --db /private/local/kidsstudio/studio.sqlite pause
    studioctl --db /private/local/kidsstudio/studio.sqlite resume

`get` and `cancel` accept a specific job id. The CLI does not expose
claim/heartbeat/complete; these are local Python API operations reserved for
future worker adapters and enforce worker identity/generation.

## Durable contract

Job state progression: QUEUED -> LEASED -> COMPLETED/FAILED, or
QUEUED -> LEASED -> QUEUED after a retryable failure or expired lease.
Owner cancellation changes pending/leased jobs to CANCELLED.

`request_key` idempotency ensures duplicate identical enqueue requests return
the same job. Different data with the same key fails closed.

`claim(worker_id, capabilities, lease_seconds)` returns one lease object with
`generation`, `attempts`, and `lease_expires`. Successful result submission,
failure submission and heartbeat must match that exact lease and be made before
it expires. Reclaiming a dead worker increments generation and attempts, so
a late previous worker cannot falsely complete the job.

**Important boundary:** database fencing prevents stale results being accepted;
it does NOT guarantee exactly-once real-world side effects. A ComfyUI job
already queued on a Mac may still render after a lease has expired, so future
worker adapters must use durable per-job idempotency, check cancellation
before each external action, and avoid duplicate paid/irreversible actions.

**Clock health:** lease expiry uses the authoritative coordinator's UNIX
clock. Pi time must be checked/synchronized before enabling worker claims,
especially after cold boots without internet. Sudden clock changes can cause
premature expiry. The next runtime milestone adds clock-health monitoring and
heartbeat refusal on a visibly invalid clock.

## Testing / limitations

Offline unit tests cover concurrent claims, reopen after restart, idempotency,
sensitive payload keys, pause/cancel, heartbeat and lease expiry, stale fence,
retry caps and CLI. The queue is currently a library + operator CLI; no daemon,
API server, Telegram command bot, editor agent, Mac execution worker or YouTube
publisher is running.

Never store users' video/voice files or child data in this database. Use a
separate archive with hashes/rights metadata when production is deployed.
