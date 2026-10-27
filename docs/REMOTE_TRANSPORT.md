# KidsStudio — Pi ↔ Mac secure coordinator prototype

This subsystem is designed for the user's **Raspberry Pi 4 coordinator** and
**Mac M3 Max execution worker**. It does not assume the user's devices are
connected to this chat; **no services have been installed or started** on
their computers.

## Implemented in repository

- Pi alone opens a dedicated local SQLite database, private artifact folder
  and HTTPS coordinator server.
- Mac initiates requests to Pi. No SQLite files shared by Synology, SMB/NFS,
  Dropbox or GitHub.
- HTTPS only for client, with system certificate verification or an
  operator-pinned CA file. No `--insecure` and no proxy/redirect forwarding.
- Bearer token (minimum 32 chars) per named worker from an environment
  variable. Pi-side worker capabilities are an allowlist; HTTP request
  cannot expand them.
- Strictly **script_draft** and **editorial_review**; other queued kinds stay
  untouched. No remote arbitrary code, ComfyUI or publish controls.
- Generation-bound leases; cancellation, expiry or wrong worker prevent
  completion. Every request has bounded JSON size and checks local/server
  time within 120 seconds. Pi cold boot clock must be fixed before use.
- Pi vault stores full returned text as exclusive private `0600` file;
  SQLite stores path/hash/provider ID, not the full script or API key.
- Auto-review receives text only after verifying the exact completed parent
  revision and SHA-256. Different reviewer provider ID is required.
- One-shot Mac worker defaults to free-labelled provider profiles, no paid
  models/fallback, no background loop; all remote output is **UNVERIFIED**.

## Non-secret provisioning example (not a live deployment)

Pi (local configuration, protected TLS key and token *already provisioned*):

    studioctl --db /private/kidsstudio/state.sqlite init
    studio-coordinator \\
      --db /private/kidsstudio/state.sqlite \\
      --vault /private/kidsstudio/vault \\
      --bind 127.0.0.1 --port 8765 \\
      --tls-cert /private/kidsstudio/pi.crt \\
      --tls-key /private/kidsstudio/pi.key \\
      --worker-id mac-ai-01

The token must be available on the Pi as `KIDS_STUDIO_WORKER_TOKEN`.
To accept connections from a different computer, restrict a dedicated
LAN interface/firewall to the Mac and provision a Pi TLS certificate
whose SAN matches the Pi DNS name/IP. Do **not** publish port 8765 to
the Internet or attach it to the existing StageCore Cloudflare tunnel.

Mac (with the same worker token provisioned locally outside Git):

    studio-remote-worker \\
      --coordinator https://YOUR-PI-DNS-NAME:8765 \\
      --ca-cert /private/kidsstudio/pi.crt \\
      --providers /private/kidsstudio/providers.local.json \\
      --worker-id mac-ai-01 --once

This uses the previously configured multi-API chat router; provider
profiles support OpenAI-compatible chat endpoints, and native protocols
still require adapters.

## CI security/integration proof

Unit and loopback TLS tests generate a **temporary self-signed certificate**
using OpenSSL, open an actual HTTPS listener, and verify:
- Wrong/missing bearer token rejected before leasing.
- Untrusted certificate refused by Mac client.
- TLS + working worker creates a script draft, completes, queues independent
  review and fetches only the pinned Pi original.
- Unauthorized job kind is never claimed.
- Cancelled lease cannot be completed later.
- Tampered Pi source draft fails closed.
- A single job can never become public publishing approval.

No real AI requests or paid inference are involved in GitHub CI.

## Limitations / remaining work

This is a prototype without production provisioning or a persistent
process manager. **Do not expose it publicly yet.** Security work remains:
per-device credential rotation/revocation, mTLS/least-privilege enrollment,
LAN firewall, rate limiting and denial-of-service controls, operational
metrics without private data, time sync and drift detection, safe broker
reconnect and exactly-once side effect prevention for expensive workloads.
A provider can change real billing without our knowledge; check cost and
enforce provider-level hard caps independently.

The remote client is restricted to editorial text jobs. Real Mac
ComfyUI/Godot tasks must get their own resource/rights sandbox and separate
approved worker adapter before any overnight autonomous media production.

## Media capabilities (separate, restricted role)

Starting with the next software revision, the coordinator supports
`character_generate` and `godot_render` in addition to editorial jobs.
This access must be **granted explicitly** with `--worker-kinds` on a
dedicated worker identity; the default remains editorial-only. A worker
may call `/v1/complete-media` to submit SHA256/status/size of a Mac-local
result — media bytes are **not** copied to Pi by this API.

This addition is only an integration/development prototype. Media workers
must be restricted to their own Mac, local vetted recipes, known TLS endpoint,
private per-worker token, and never offered over a publicly exposed listener.
See [MEDIA_WORKER.md](MEDIA_WORKER.md).
