# KidsStudio agent instructions

Read `README.md`, `docs/ARCHITECTURE.md`, `docs/STUDIO_QUEUE.md`, `docs/ROADMAP.md` and `docs/PRODUCTION_INTELLIGENCE_INTEGRATION.md` before modifying production workflows.

## Working agreement
- Use `feature/production-intelligence-safe-integration` for this workstream. Do not create per-agent branches.
- Preserve `main` and existing queue, lease fencing, worker journal, pinned recipe, immutable SHA provenance and owner-publication approval contracts.
- Prefer small, testable commits on the same integration branch. Serialize changes to shared files; do not merge untested work.
- Diagnose before fixing; add a regression test for each confirmed bug.
- Separate deterministic tests from real Mac/Pi tests. Never claim a CI or hardware PASS without evidence.
- Keep secrets, source artwork, private scripts, model weights and videos out of public Git.
- Do not trigger paid providers, downloads, persistent services, external uploads or public publishing without explicit approval.
- Use existing bounded review/repair and durable queue rather than building duplicate orchestrators.
- Record decisions, known failures, test evidence and rollback points in issue #32 and the integration register.

## Definition of done
Code, focused tests, regression evidence, docs, rollback procedure, and a reviewed integration decision. Passing technical checks never authorizes public release.
