# M51 — No-bypass final montage render contract

**Scope:** Draft PR #28, code-only; no owner Mac or Pi devices accessed,
no model inference, no YouTube OAuth, upload or publication.

## Problem found in M50 audit

M50 atomically checked the coordinator's original plan SHA and deferred
catalogue binding when `StudioOrchestrator.tick()` submitted final render.
However, the existing `studio-series queue-render` command calls
`SeriesManager.queue_render()` directly. For an M32-managed episode this
could skip M32's plan/recipe contract and (for AFTER_SCENE_QA)
its verified M49 catalogue binding. A direct caller could pass a
64-character SHA without proving that it was the plan's exact SHA.

## M51 changes

1. `StudioOrchestrator.initialize` creates an additive immutable
   `studio_orchestrator_render_contracts` table.
2. `pin` stores in one transaction the M32 plan SHA, final montage recipe
   ID, the original catalogue SHA or AFTER_SCENE_QA marker, and a
   canonical SHA of **ordered scene numbers + source script hashes**.
3. `status` fails closed if a contract is missing or disagrees with the
   exact current owner-supplied plan. No automatic repair/re-pin occurs.
4. `SeriesManager.queue_render` detects M32 plan records. For those
   episodes it refuses the older unguarded series CLI route. A guarded
   request must prove the matching plan SHA, currently ACTIVE series,
   registered original scene-plan SHA, approved complete scene receipts,
   immutable recipe ID, exact catalogue policy, original scene identity
   fingerprint, and (for deferred catalogues) the current frozen M49
   catalogue + scene-set binding. All checks occur **inside the same
   SQLite write transaction that inserts the render job**.
5. Older M13-only (not registered in M32) owner-controlled render calls
   retain their previous checks and behaviour. The code does not make
   the generic SQLite queue an external security boundary.

## Synthetic tests

- A fully approved deferred M32 episode cannot queue via the older
  `SeriesManager.queue_render` path before **or after** M49 binding.
- A guarded caller cannot substitute a different recipe ID or arbitrary
  catalogue SHA into a legacy pre-pinned M32 episode.
- A missing contract blocks M32 status/tick and direct guarded enqueue.
- Scene-script row mutation after a green M32 status cannot dispatch.
- The valid two-scene M32 path still queues one private final job.

## Upgrade considerations

New M32 plans are pinned together with contracts. Existing databases
that contain pre-M51 pinned M32 plans have no contract row and will
**fail closed** until a future explicit owner-authorized, source-verified
reconciliation procedure is implemented. Do not delete or overwrite
the old M32 plan row to bypass the migration block. Preserve DB backups.
This is conservative and intentional.

## Trust boundaries

The protection applies to M32-managed episodes going through
`SeriesManager.queue_render`, including the existing series CLI.
It does not claim to prevent arbitrary local Python code with write
access to the SQLite file from inserting a synthetic job. Local device
security, TLS worker authorization, Mac M16 original-media byte checks,
independent child-safety/rights assessment, and owner-reviewed PRIVATE
preview remain separate required gates.

Keep PR #28 DRAFT and unmerged; CI and real-device testing must be
reported separately.
