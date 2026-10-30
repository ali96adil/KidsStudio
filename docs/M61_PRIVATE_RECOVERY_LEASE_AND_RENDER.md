# M61 — Dedicated private recovery lease + FFmpeg assembler

**Scope:** KidsStudio draft PR #28. M61 adds real software paths but **does not
claim owner Mac/Pi hardware qualification**, local model quality, a real
video upload, M14 original owner-signature attestation, or any permission
to publish on YouTube. Existing main remains unchanged.

## Why a dedicated kind

The previous M60 job ID was *reserved* outside the ordinary jobs table.
Original M52–M54 `episode_assemble` guards expect M32's original
`render_job_id` and M49 catalogue SHA, so inserting a recovered
scene-set into that kind would bypass those checks or always fail.
M61 introduces a completely separate, one-shot
`recovery_assemble` **capability and lease namespace**.

## Pi: immutable one-shot recovery lease

`kidsstudio/recovery_lease.py` adds an additive
`studio_recovery_leases` table. The local Pi operator explicitly
activates an existing M60 reservation against the exact copied M56
proposal file SHA, after reconfirming current M32/M49/M51 source,
original FAILED/CANCELLED job, BLOCKED episode, approved scene
voice/LTX/audio QA, M57 intent, M58 binding and M59 staged recipe.
Activation grants no publication rights.

The Mac must use a separately authorized worker credential with the
`recovery_assemble` capability. The coordinator provides **separate**
authenticated routes:

- `recovery-claim`: exact configured proposal ID, one lease, no source paths
- `recovery-pre-execution-check`: revalidate all Pi pins before rendering
- `recovery-heartbeat`: renew bounded lease only after full Pi recheck
- `recovery-complete`: accept an M7 technical master receipt for owner
  review, never public release
- `recovery-fail`: terminal quarantine; no automatic replay

A missing, expired, revoked, paused, altered or replayed lease is terminal
for this recovery job. Expired leases are **never requeued**; any
ambiguous Mac STARTED journal requires explicit reconciliation. The Pi
audit references the original queue job so the foreign-key chain remains
valid. A general media worker cannot claim recovery work.

The recovery result state is
`M61_RENDERED_PENDING_FINAL_M7_OWNER_REVIEW`, meaning the worker has
claimed technical success **only**. The Pi does not inspect Mac bytes
remotely, does not automatically authorize them, and never promotes a
video to public visibility. Existing educational, licensing, AI visual
checks and final owner's PRIVATE preview remain pending.

### Local activation boundary

The `RecoveryLeaseGate.activate(...)` method runs on the Pi with
private access to the copied M56 proposal and M60 reservation. It is
not exposed over the ordinary TLS worker API. Thus the remote worker
cannot self-activate an arbitrary incomplete recovery.

## Mac: dedicated renderer

`kidsstudio/recovery_remote_worker.py` uses the same authenticated
outbound-only HTTPS client, with a fixed configured original Mac
payload, original job ID, proposal ID and original private static
media catalogue. The Pi never transmits file paths or shell commands
and the ordinary `EpisodeAssembler` still rejects schema-2 staging
recipes.

The Mac worker reserves the NEW Pi job ID in the durable local
`MediaJournal` as STARTED before rendering, and refuses replay. It
heartbeats continuously; any lease/network failure sets a cooperative
abort event and causes the FFmpeg subprocess group to terminate using
the existing M54 runner.

`kidsstudio/recovery_render.py` verifies exact M59 frozen recipe/manifest
against original SHA-pinned script, original LTX sources, frozen M55/M56
and M58 contracts. It also performs a **new complete FFmpeg M7 decode**
of each recovered normalized scene before creating the render folder.
The render ID is the newly reserved Pi job ID, not the original failed
job or proposal ID.

Each scene preserves order:
- Technically valid previously normalized scenes are copied and SHA
  verified into the new private render folder, **without a second
  individual FFmpeg normalization/face pass**.
- Missing normalized candidates fall back to their originally approved
  LTX video with original face-processing policy and standard 720p/24fps
  normalization.
- A new master is stitched with FFmpeg at 24fps and AAC 48kHz. Its
  timing/geometry is checked and its *entire video and audio* must pass
  the complete M7 decode plus SHA check before a technical receipt may
  be sent to Pi.

Any failure or lease revocation preserves the private run directory with
`M61_FAILED_REQUIRES_MANUAL_RECONCILIATION` QA report. It cannot trigger a
blind second attempt. Even successful media remains for quality checks,
rights/educational checks and final human-owner PRIVATE preview.

## Tests

Synthetic M32 two-scene Pi tests check isolated recovery capability,
exact targeted Pi claim, M53-like pre-execution proof, heartbeat renew,
master technical receipt, no ordinary queue entry, terminal lease expiry,
paused-studio cancellation and wrong generation.

Synthetic Mac tests check a recovered first scene is copied without
per-scene re-encoding while the second scene is normalized; master
technical M7 receipt; changed live Pi proof refuses before any output;
lease abort quarantines media. Remote worker unit tests verify durable
one-shot journal behavior, uncertain completion acknowledgements never
render twice and unexpected payload fields fail before claim.

Injected synthetic fake media/FFmpeg/remote clients test control
decisions. A separate real-FFmpeg integration test on CI generates
synthetic color/audio clips, verifies that a normalized clip is not
re-encoded individually, and runs full M7 master decode. That test
intentionally mocks M55–M60 lineage checks to isolate the media
engine and is **not** a real owner Mac/Pi hardware qualification.

## Offline operator commands (reference only)

M61 exposes a **Pi-local** activation CLI and a separate Mac worker CLI.
Activation is not permitted over the worker TLS API. Do not use these
against owner devices before staged qualification.

```sh
# Pi: requires M60 reservation and its original private M56 file.
python -m kidsstudio.recovery_lease \
    --db /PRIVATE/pi/studio.sqlite --initialize
python -m kidsstudio.recovery_lease \
    --db /PRIVATE/pi/studio.sqlite --activate \
    --proposal /PRIVATE/pi/copied_m56_proposal.json \
    --sha256 EXACT_COPIED_M56_FILE_SHA256

# Mac: WITHOUT --execute, this is strictly dry-run (no network).
# With --execute, token is read from KIDSSTUDIO_WORKER_TOKEN.
python -m kidsstudio.recovery_remote_worker \
    --pi-url https://PRIVATE_PI_HOST:PORT \
    --worker-id mac-recovery \
    --ca-file /PRIVATE/mac/pi-ca.crt \
    --recipes /PRIVATE/mac/approved_media_catalogue.json \
    --journal /PRIVATE/mac/media_journal.sqlite \
    --original-job-id ORIGINAL_32_HEX_ID \
    --proposal-id NEW_32_HEX_ID \
    --original-payload /PRIVATE/mac/original_payload.json
```

For actual operation **only after device qualification**, provision
a separate `recovery_assemble` worker credential and invoke the Mac
command with `--execute`. Neither CLI has a PUBLIC upload operation.
The final M7 full decode and the recovered-byte copy monitor the
lease-abort signal continuously; any revoked claim quarantines the run.

The tests include one **real FFmpeg/FFprobe media integration** using
synthetic red/blue scenes and a full decoded master. That isolated
renderer test mocks earlier M55–M60 contract checks to focus on the
video pipeline; separate source/contract/lease tests cover those checks.
No integration test equates to owner Mac/Pi hardware qualification.

## Activation, owner review, next milestone

M61 activation requires an already initialized Pi recovery lease table,
an exact M60 reservation and the original M56 proposal file copied to
Pi privately. A worker with `recovery_assemble` credential and fixed
Mac sources can then run exactly one recovery attempt. Do **not**
activate on the owner Mac/Pi before a supervised qualification.

A completed technical receipt is **not** a pass for overall video
quality, educational benefit, character consistency, voice rights,
kids safety, a YouTube PRIVATE upload, or public publication. These
require a separate M62 reconciliation/integration bridge and the
owner's final private preview. No default PUBLIC switch has been added.
