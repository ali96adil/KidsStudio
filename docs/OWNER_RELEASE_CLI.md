# Owner release decisions (local-only)

Release authorization is a separate action from the review form. This CLI
writes a release decision but **never publishes or changes YouTube visibility**.

First review the video and record `approved` in the review database. Then:

```bash
python -m kidsstudio.owner_release_cli \
  --review-db ~/kidsstudio-data/reviews.sqlite \
  --release-db ~/kidsstudio-data/release.sqlite \
  status --episode red-ar

python -m kidsstudio.owner_release_cli \
  --review-db ~/kidsstudio-data/reviews.sqlite \
  --release-db ~/kidsstudio-data/release.sqlite \
  decide --episode red-ar --actor owner --decision release_authorized
```

To revoke authorization, run `decide` with `--decision hold`.
The CLI refuses `release_authorized` unless the latest creative review
is `approved`. Later review changes invalidate eligibility.

Security note: `--actor` is an audit label, not proof of identity. Run this
CLI only in a trusted local administrative environment. Production phone
authorization will require authenticated identity, HTTPS and CSRF controls.
