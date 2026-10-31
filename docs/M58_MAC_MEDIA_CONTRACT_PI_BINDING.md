# M58 — Mac media SHA/full-decode contract bound to Pi recovery intent

**Scope:** Draft PR #28 source code and synthetic fixtures. No physical
owner Mac/Pi, genuine media/inference, YouTube OAuth, uploads or public
release. Neither side is allowed to render a recovered montage yet.

## Why

M55 freezes a read-only inventory of interrupted private montage artifacts.
M56 proposes a separate attempt, selecting fully decoded normalized clips
when possible and falling back to their original SHA-pinned LTX sources.
M57 records a new **non-executable** recovery intent against current Pi
M32/M49/M51 scene and source lineage. Before any Pi job can be authorized
we need a stable, repeatable contract of the exact proposed media bytes.

## Mac: media contract freeze

New `kidsstudio/recovery_media_contract.py` reads the ORIGINAL Mac
STARTED journal, original job payload, immutable M55 forensic inventory,
immutable M56 proposal and currently pinned media recipe catalogue.

It rereads each original approved LTX clip SHA-256. For every selected
recovered normalized clip it rereads its original expected SHA-256 and
runs a **fresh M7 ffprobe/complete FFmpeg decode**. A previously passing
M56 check cannot stand in for this check: any source change, failed
decode, stale evidence, unexpected output file, mismatched scene index,
wrong script, changed original catalogue or old job ID fails closed.

Every scene produces fixed metadata only: scene number, original LTX
SHA-256, chosen media SHA-256, selection strategy, and a conservative
full-M7-technical-check flag. No local Mac file path is transferred to
the Pi as an executable command. The contract explicitly says media
bytes were NOT verified by the Pi, new scene provenance/FFmpeg checks
are still required, and publication/automatic execution are forbidden.

The `--freeze` option writes ONE new private, exclusive JSON envelope
at `<private output root>/_recovery_media_contracts/<proposal-id>.json`.
It includes a canonical `contract_sha256`; the CLI also prints the
SHA-256 of the **entire JSON file**. No original journal or media is
modified. Re-running the freeze cannot overwrite the first contract.

## Pi: re-validate metadata and pin once

`RecoveryIntake.initialize()` adds
`studio_recovery_media_contracts` on the existing Studio Brain SQLite
database. `RecoveryIntake.bind_media_contract` receives *two copied*
immutable JSON files plus the SHA-256 of their exact transferred file
bytes: the original M56 envelope and the new M58 media contract.

Within one Pi SQLite write transaction it repeats the M57 verification
against the CURRENT terminal original job, BLOCKED episode, ACTIVE
series, matching original request, M32/M49/M51 plan, frozen scene-set,
and independently approved Pi voice/LTX/audio receipts.

The M58 contract must match M56 **scene for scene**: original LTX SHA,
selected SHA, strategy, candidate/fallback counts, M7 claims and all
negative publication flags. A replay, forged digest, wrong SHA, changed
episode receipt or altered selection fails. The row is stored only in
`M58_MEDIA_BOUND_REQUIRES_FRESH_EXECUTION_CONTRACT`, and an audit event
is attached to the original job.

The Pi response always includes `new_pi_job_id=null`,
`pi_media_bytes_verified=false`,
`auto_execute_allowed=false` and
`public_release_authorized=false`. **A copied JSON SHA is neither a
cryptographic sender signature nor independent Pi verification of Mac
media bytes.** It pins what Pi received, not the truth of the Mac claim.
Mac media bytes must be verified again at the future execution boundary.

## Synthetic regressions

- Mac: exact original/recovered media SHA and full M7 selection checks,
  bounded immutable contract freeze, no repeat/overwrite, refusal of
  tampered M56 source or changed original LTX and false M7 claim.
- Pi: current M57 intent required, old failed job/episode and current
  M32/M49 scene QA checked again, exact M56 vs M58 selected SHA and
  per-scene technical metadata, bad file SHA/forged flags rejected,
  duplicate rejected, zero new `QUEUED` jobs.

Mac algorithm fixture uses synthetic video bytes with an injected M7
checker to test the decision policy. In actual code the default M7
checker decodes the entire video. Pi tests use forged *metadata*
specifically to demonstrate that Pi does NOT attest Mac media bytes.
Neither is a real-device qualification.

## Offline commands — only after device approval

On the Mac, with original private payload and journal:
```sh
python -m kidsstudio.recovery_media_contract \
  --recipes /PRIVATE/frozen_catalogue.json \
  --journal /PRIVATE/mac_journal.sqlite \
  --original-job-id OLD_32_HEX_JOB_ID \
  --original-payload-json /PRIVATE/original_payload.json \
  --proposal-id NEW_32_HEX_PROPOSAL_ID --freeze
```

Copy the original M56 proposal JSON and M58 contract JSON to a PRIVATE
location readable by the Pi. Then pin exactly those two files:
```sh
python -m kidsstudio.recovery_intake --db /PRIVATE/pi/studio.sqlite \
  --bind-media \
  --proposal /PRIVATE/copied_m56_proposal.json \
  --sha256 SHA256_OF_COPIED_M56_FILE \
  --media-contract /PRIVATE/copied_m58_media_contract.json \
  --media-sha256 SHA256_OF_COPIED_M58_FILE
```

These are reference commands, **not** instructions to execute against
the owner's devices yet. The Pi database needs the M57 intake schema
initialized and proposal pinned.

## Remaining M59 boundary

M58 deliberately does NOT create a new Pi render job. First a distinct
**fresh executable** montage recipe and scene provenance contract must
bind the selected recovered bytes to original M14 voice/LTX job IDs,
be tested against the existing M51/M52/M53/M54 guards, and be reverified
on Mac just before execution. New assembled master still requires full
M7/educational/rights QA and an owner PRIVATE YouTube preview.
Leave PR #28 draft/unmerged.
