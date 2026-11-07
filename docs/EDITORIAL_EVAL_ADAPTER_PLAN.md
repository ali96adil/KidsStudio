# Editorial evaluation adapter — design gate

## Existing source of truth
`LocalAIWorker.run_once` in `kidsstudio/local_worker.py` writes immutable private text and SHA metadata; `StudioQueue` owns idempotent requests, leases, generation fencing, event history and cancellation. Independent editorial review already exists. Do not create another queue or rewrite the worker.

## Proposed opt-in hook
1. After a script draft is stored, verify the exact source SHA from private artifact bytes.
2. Run `evaluate_script` against that text with an explicit language, minimum length and episode-specific required terms. Store a *separate* private eval manifest with rule version, exact source SHA, results and timestamps.
3. Treat mechanical PASS as eligibility for independent editorial review only, never as approval.
4. If checks fail, mark as REVISE_REQUIRED in the evaluation record; do not silently enqueue unlimited retries. The existing queue contract must remain authoritative.
5. Keep review provider independent from the original writer; verify hashes again before review.
6. Do not write evaluations into public Git or alter production SQLite schema without a migration and rollback test.

## Failure tests required before implementation
- Tampered source SHA; missing source; wrong language; Unicode normalization mismatch.
- Cancelled/stale lease; duplicate request; exhausted retries; independent reviewer unavailable.
- No paid fallback; no private script leakage; no publishing side effects.

## Rollback
The evaluator must remain disabled by default and be removable without changing existing queue job schemas or worker output manifests.
