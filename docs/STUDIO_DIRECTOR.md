# Studio Director proposal ledger v0.1

The first Director component is a **local proposal and decision ledger**, not
an autonomous LLM agent. It records caller-supplied evidence as unverified,
requires alternatives and a written rationale, and can enqueue an explicitly
accepted proposal through the existing `StudioQueue` API. It performs no
research, model call, network request, job execution, spending, upload or
publication.

## Setup

Create an existing private directory outside the Git checkout. Keep both the
Director database and the existing queue database on local storage, not a
network share:

```sh
umask 077
mkdir -p "$HOME/kidsstudio-private/control"
chmod 700 "$HOME/kidsstudio-private/control"
studio-director --db "$HOME/kidsstudio-private/control/director.sqlite" init
studioctl --db "$HOME/kidsstudio-private/control/queue.sqlite" init
```

The proposal input is a private JSON file with this shape:

```json
{
  "title": "Colors through play",
  "summary": "A short story introduces colors through everyday objects.",
  "audience": "ages 4-6",
  "learning_objective": "Identify red and blue objects.",
  "alternatives": [
    {"option": "story", "rationale": "Supports recall in context."},
    {"option": "worksheet", "rationale": "Lower production effort."}
  ],
  "evidence": [
    {"source": "owner-note-01", "observed_at": "2026-11-11",
     "claim": "The owner supplied a request for color-recognition topics.",
     "sha256": null}
  ],
  "job_kind": "script_draft",
  "job_payload": {"language": "ar", "topic": "الألوان", "auto_review": true}
}
```

`source` is a caller-supplied reference, not a fetched or verified source.
`sha256` may be null when the source bytes are not available locally. The
record labels each evidence item `CALLER_SUPPLIED_UNVERIFIED`. Do not place
personal data, children's data, credentials, raw scripts, artwork or media in
the proposal. Proposal and queue JSON reject credential-shaped fields and
values.

Record and inspect a proposal:

```sh
studio-director --db "$HOME/kidsstudio-private/control/director.sqlite" \
  propose --request-key colors-story-v1 --proposal-json /private/path/proposal.json
studio-director --db "$HOME/kidsstudio-private/control/director.sqlite" \
  show --proposal-id PROPOSAL_ID
```

Decision actors are labels, not authenticated identities. A decision is
immutable; creating a successor proposal with `supersedes_id` retains the old
record and supports re-evaluation with new evidence. The ledger does not claim
that the named actor is the Director or owner.

```sh
studio-director --db "$HOME/kidsstudio-private/control/director.sqlite" \
  decide --proposal-id PROPOSAL_ID --outcome ACCEPTED \
  --actor director.editorial --rationale "Evidence supports the story format."
studio-director --db "$HOME/kidsstudio-private/control/director.sqlite" \
  enqueue --proposal-id PROPOSAL_ID \
  --queue-db "$HOME/kidsstudio-private/control/queue.sqlite"
```

Only an accepted decision can enqueue a job. The existing queue's allowlisted
job types, sensitive-field rejection and request-key idempotency remain in
force. Repeating `enqueue` returns the same queue job; it does not execute it.
Workers remain independently configured and single-shot. Rejected and deferred
proposals create no job. Queue insertion and Director-ledger linkage use two
local SQLite databases; if interrupted between them, the deterministic queue
request key makes a retry link to the same job rather than creating another.

The internal trial path sets `auto_review` on its `script_draft` queue job.
After the draft worker writes a private artifact, the existing queue operation
atomically completes that job and creates a separate `editorial_review` job
bound to the exact draft SHA and writer provider. The review worker must use a
different provider. This second review result remains
`EDITORIAL_REVIEW_UNVERIFIED`; neither it nor the earlier concept review
approves publication.

## Qualification boundary

Unit tests cover validation, evidence/rationale digest binding, immutable
decisions, successor links, secret/symlink/private-file rejection, and accepted
versus rejected queue handoff. No source connector, autonomous decision model,
human identity verification, cost estimator, verified analytics, or real
research source is implemented. The owner retains all spend, external-contact,
commercial and public-publishing decisions.

## Aggregate outcome measurement scaffold

`StudioDirector.record_measurement(...)` appends a small aggregate outcome
record to a completed, accepted proposal. Each record is bound to a caller-
provided episode-version SHA-256 and an idempotency request key. Supported
numeric fields are `views`, `watch_time_seconds`,
`average_view_duration_seconds`, `likes`, `comments`, `shares`, and
`subscribers_gained`; unknown fields and negative, non-finite, boolean, or
out-of-range values are rejected. There are no per-child IDs, demographic
rows, comments, or free-text metric names.

The source is only `OWNER_SUPPLIED_AGGREGATE` or
`AUTHORIZED_EXPORT_ASSERTION`. These are caller assertions, not authenticated
permissions or source verification. Every record is labeled
`CALLER_SUPPLIED_UNVERIFIED`; a digest binds the stored measurement bytes but
does not prove that the source is real or that the episode SHA is correct.
The feature does not contact YouTube or another analytics service, infer
missing data, calculate profitability, authorize spending, or make a
publication/commercial decision. Use `list_measurements(proposal_id=...)` for
local review. Changing data under an existing request key is rejected; record
a new key when corrected or newly observed evidence is supplied.

This is an ingestion and audit foundation only. Actual authorized-source
adapters, analytics validation, learning policy and commercial scenario
analysis remain unimplemented and require separate qualification.

An internal AI trial that supersedes an earlier proposal must supply and have
its independent proposal cite at least one evidence item whose source, date,
claim, or excerpt material differs from the earlier proposal's recorded
evidence. Renaming an evidence ID does not count. This prevents a failed
concept from being requeued as if the supersession link alone were new
information. The guard compares supplied text only; it does not verify source
authenticity, factual truth, research freshness, or educational quality.
