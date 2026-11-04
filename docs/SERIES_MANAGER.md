# Series Manager / Episode Pipeline M3

**Branch-stage feature only:** no deployment, migration of old standalone
Control Center, live Mac or Pi configuration, API requests, GPU rendering,
YouTube publishing or recurring background agents have been performed.

The canonical GitHub repo has Studio Brain, one-shot AI workers and separate
Mac media worker prototypes. Earlier Control Center v1–v3 ZIP deliveries are
**not yet part of GitHub main** and store data in a separate SQLite schema.
Do not copy a ZIP database directly into the Studio Brain database; it
requires a later explicit, tested migration.

## Production rules

1. A **series** includes a fixed, ordered syllabus; sample: 12 color lessons.
   Arabic letters 28 and English letters 26 are separate future planned series.
2. Only one series is ACTIVE. Switching requires explicit pause and reason,
   or full internal production completion.
3. Idle scheduling fills **at most 3 unfinished episode slots**, in curriculum
   order. It queues the existing allowlisted script_draft worker kind with
   auto_review enabled. Planning by itself makes **no provider requests**.
4. A completed draft and its independent reviewer must be reconciled from
   Studio Queue; both model outputs remain **unverified**.
5. Owner reviews the exact draft/hash, makes a separate script decision, and
   explicitly queues a known Mac-local pinned Godot media recipe.
6. A valid MP4 **receipt** is only RENDERED_QA_PENDING. Owner verifies the
   actual video, sound, character integrity, pedagogic quality and rights.
7. A series is internally COMPLETED only after every episode has explicit
   owner audiovisual approval. COMPLETED does **not** imply publication.
8. BLOCKED episodes do not retry on their own; retry is owner-initiated,
   journalled, and uses a fresh idempotency generation.

Secrets, scripts, artwork, models and video binaries stay OUTSIDE Git and
are not returned in the dashboard snapshot. This module is a local operator
tool, not an open network dashboard.

## Local commands — examples for a future integrated test, NOT for running now

The SQLite file is the same existing local Studio Brain DB, not on a NAS.

    DB=/private/local/kidsstudio/studio.sqlite
    python -m kidsstudio.series_cli --db "$DB" init
    python -m kidsstudio.series_cli --db "$DB" add-series \
      --plan examples/colors_series_ar.json --activate
    python -m kidsstudio.series_cli --db "$DB" prepare --limit 3
    python -m kidsstudio.series_cli --db "$DB" status

Use studio-worker --once with an explicitly configured local profile to
process an editorial task, then:

    python -m kidsstudio.series_cli --db "$DB" sync
    python -m kidsstudio.series_cli --db "$DB" note colors-ar \
      --episode 1 --text "Check the red ball visual reference"
    python -m kidsstudio.series_cli --db "$DB" approve-script colors-ar 1 \
      --sha256 EXACT_VERIFIED_DRAFT_SHA256 --note "I checked the full script"
    python -m kidsstudio.series_cli --db "$DB" queue-render colors-ar 1 \
      --recipe OWNER_PINNED_LOCAL_GODOT_RECIPE

A Mac media worker must separately validate the pinned recipe on the actual
machine. Its result only moves the episode to QA_PENDING; the owner still
approves the final episode by a distinct command, and **public release
is a separate later permission-gated milestone**.

## Remaining interfaces before real production

- Reconcile this schema with standalone Control Center v3 UI and its database.
- Link an approved script hash to a specific immutable scene recipe, rather
  than relying on owner review of that relation.
- Make Chatterbox audio, LTX animation, Bunny v07 cleanup, FFmpeg assembly,
  language-specific quality checks and voice commercial rights provenance
  distinct approved stages. The existing Godot smoke render is not an LTX
  lip-sync integration.
- Add explicit owner-only dashboard API; never expose direct SQLite.
- Run a full isolated database regression, then one end-to-end Mac/Pi and
  audiovisual acceptance gate when requested after building the phases.
