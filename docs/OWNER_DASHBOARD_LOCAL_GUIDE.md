# Kids Studio local owner review and dashboard

This prototype operates on **local files only**. It does not start a server,
connect to YouTube, publish media, or execute worker tasks.

## 1. Initialize the queue (once)

Use the existing `studioctl init` command for the Pi-local queue database.
Do not store operational databases inside the Git checkout.

## 2. Record a review decision

```bash
python -m kidsstudio.owner_review_cli --journal /path/to/private/reviews.json record --episode red-ar --state changes_requested --note "Adjust narration"
python -m kidsstudio.owner_review_cli --journal /path/to/private/reviews.json record --episode red-ar --state approved --note "Reviewed"
python -m kidsstudio.owner_review_cli --journal /path/to/private/reviews.json list
```

Approval in this journal is a **review record only** and never changes
YouTube visibility. No publish endpoint exists in these modules.

## 3. Export one offline dashboard

```bash
python -m kidsstudio.owner_dashboard_combined \
  --db /path/to/private/studio.sqlite \
  --series examples/owner_series_colors.json \
  --reviews /path/to/private/reviews.json \
  --out /path/to/private/owner-overview.html
```

Open the resulting HTML locally. The exporter refuses to overwrite an
existing HTML file: choose a fresh output filename for each export.
The dashboard intentionally excludes private notes, prompts and job payloads.

## 4. Boundaries

- Series JSON is currently a separate planning manifest, not a live
  authoritative production state.
- Review journal has no multi-writer locking; only one review writer should
  use a journal at a time until transactional storage is implemented.
- Dashboard HTML is a snapshot, not a live web interface.
- Run end-to-end tests on the actual Mac and Raspberry Pi before production.
