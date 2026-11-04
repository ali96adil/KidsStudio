# M21 — Live, authenticated Pi scene readiness preflight (NO execution)

Status: **Draft PR #28 source and synthetic localhost TLS tests only**.
Nothing has been installed or contacted on the owner's Mac/Raspberry Pi.
No model, paid service, browser, media upload or publishing is invoked.

## Why M20 needed a live check

M20 verifies an exact SHA256-pinned standalone Studio Brain backup against
the same M19-approved two-scene Mac source files. A sound backup cannot
guarantee that the live Pi has not since been paused, revised or started
another job. M21 re-reads the current Studio Brain records over existing
authenticated **HTTPS**, using the existing per-worker bearer token,
certificate validation, Pi/Mac clock comparison, and a fresh random nonce.

This is a read-only status observation at a point in time. A passing check
NEVER leases work, arms the GPU or grants permission to run Chatterbox.
The coordinator may change immediately afterwards. A later owner-approved
model operation must independently acquire and revalidate a unique current
lease against an approved local recipe and exact scene script SHA.

## Design

- Coordinator route: `POST /v1/pilot-readiness`. The normal HTTPS and
  bearer-token handlers authenticate the worker first. The worker must
  have explicitly granted `voice_synthesize` capability. The endpoint
  rejects standard editorial workers and cannot be called without TLS.
- Strict bounded request contains **only** nonce, series ID, episode
  number/revision, the registered plan SHA, parent script SHA, and ordered
  scene script + normalized objective SHA values. No source dialogue,
  private art, video, file paths, API key, arbitrary command or model
  instructions are transmitted.
- On Pi, an SQLite deferred read transaction consistently checks:
  coordinator not paused, exactly one active series, current approved
  parent revision and audit, immutable M13 plan SHA, the two scene
  identities/text-objective hashes and **no prior M13 stage work**.
  No schema migration, files, job lease, queue operation or SQLite write.
- The Pi echoes the nonce and exact validated pins in an intentionally
  non-authorizing response, with the observation time and safe boolean
  fields. The existing TLS client also enforces Pi/Mac clock compatibility.
- On Mac, `studio-live-m13-preflight` first reruns the full M19/M20
  offline checks, sends a freshly generated 128-bit nonce over the
  established HTTPS channel, rejects stale/mismatched response payloads,
  verifies all exact fields and re-hashes its local plan and snapshot
  after the request.
- The final status is
  `OFFLINE_AND_LIVE_M13_AGREE_OWNER_EXECUTION_NOT_AUTHORIZED`. It means
  the selected target episode matched **when observed**. It does **not**
  establish the entire snapshot is current, certify the Pi hardware,
  prove the commercial voice/model rights, or grant permission to publish.

## Future owner-device check — not run now

Only after separate authorization, ensure the existing local Pi coordinator
is serving HTTPS with its approved certificate and a worker token assigned
`voice_synthesize`. Use the owner-controlled network, not an arbitrary
public host. Place an M9 consistent, *standalone* Pi backup below the
approved Mac root and pin its SHA256 as explained in M20.

```bash
studio-live-m13-preflight \
  --coordinator https://OWNER-PI-HOST:8765 \
  --ca-cert /PRIVATE/KidsStudio/certs/pi-ca.pem \
  --worker-id mac-voice-01 \
  --token-env KIDS_STUDIO_WORKER_TOKEN \
  --mac-contract /PRIVATE/KidsStudio/mac_contract.json \
  --scene-plan /PRIVATE/KidsStudio/scene_plan.json \
  --scene-plan-sha256 EXACT_REGISTERED_M13_PLAN_SHA256 \
  --scene-1-script /PRIVATE/KidsStudio/scripts/scene01.txt \
  --scene-1-voice-recipe /PRIVATE/KidsStudio/recipes/scene01_voice.json \
  --scene-2-script /PRIVATE/KidsStudio/scripts/scene02.txt \
  --scene-2-voice-recipe /PRIVATE/KidsStudio/recipes/scene02_voice.json \
  --pi-snapshot /PRIVATE/KidsStudio/snapshots/m13.sqlite \
  --pi-snapshot-sha256 EXACT_SNAPSHOT_SHA256
```

The worker token stays in an environment variable. Do not share it,
run it with `set -x`, embed it in a GitHub issue, or put it in the
repository. The CLI prints a redacted report, with no private file paths.

## CI evidence and limitations

The added tests use real TLS 1.2+, a freshly generated localhost CA-trusted
certificate, actual HTTP request handling and the existing immutable
SQLite backup + M13 ledger. They check successful read-only observation,
nonce reflection/tamper rejection, wrong token, wrong worker capability,
untrusted certificate, paused current series, and already started scene
jobs. All models and content are synthetic fixtures.

Current live observations can become stale immediately; this is why a
successful probe is **not** a job reservation. No auto-retry, no background
daemon, no media generation, no YouTube upload.

**Still pending:** the real owner Pi/Mac network test, actual Chatterbox
Multilingual MLX adapter/voice rights check, actual LTX 2.3 MLX output,
original Bunny art QA, per-scene owner audio/visual approval, complete
M7 master review, independent backup restore and explicit release approval.
