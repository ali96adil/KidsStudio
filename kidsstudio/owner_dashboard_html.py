"""Offline, read-only owner dashboard; no server, JS, network or credentials."""
from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from .owner_dashboard_snapshot import snapshot

LABELS = {
    "QUEUED": "Waiting",
    "LEASED": "In progress",
    "COMPLETED": "Completed",
    "FAILED": "Needs attention",
    "CANCELLED": "Cancelled",
}

def render(data: dict) -> str:
    """Render only the already-sanitized snapshot using HTML escaping."""
    counts = data["counts"]
    cards = "".join(
        '<div class="metric"><span>' + escape(LABELS.get(state, state)) +
        '</span><strong>' + str(int(count)) + '</strong></div>'
        for state, count in sorted(counts.items())
    )
    rows = "".join(
        "<tr><td>" + escape(str(job["job_id"])) +
        "</td><td>" + escape(str(job["kind"])) +
        "</td><td>" + escape(str(job["state"])) +
        "</td><td>" + str(int(job["attempts"])) + "</td></tr>"
        for job in data["recent_jobs"]
    )
    if not rows:
        rows = '<tr><td colspan="4">No jobs yet</td></tr>'
    paused = "Paused" if data["paused"] else "Accepting work"
    failed = int(data["attention"]["failed_in_recent_window"])
    truncated = "Showing a limited recent window, not all jobs." if data["recent_window"]["truncated"] else "All jobs are included in this window."
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Kids Studio | Owner Overview</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,sans-serif}
body{max-width:1100px;margin:2rem auto;padding:0 1.2rem;line-height:1.5}
header{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:.8rem;margin:1.5rem 0}
.metric{padding:1rem;border:1px solid #8887;border-radius:12px}
.metric span{display:block}.metric strong{font-size:2rem}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:.7rem;border-bottom:1px solid #8886;overflow-wrap:anywhere}
.table-wrap{overflow-x:auto}.note{opacity:.8}footer{margin-top:2rem;font-size:.85rem}
</style></head><body>
<header><div><h1>Kids Studio</h1><p>Owner overview · read-only offline snapshot</p></div>
<strong>""" + escape(paused) + """</strong></header>
<section aria-label="Queue states" class="metrics">""" + cards + """</section>
<section><h2>Attention</h2><p>Failed jobs in recent window: <strong>""" + str(failed) + """</strong></p>
<p class="note">""" + escape(truncated) + """</p></section>
<section><h2>Recent jobs</h2><div class="table-wrap"><table>
<thead><tr><th>Job ID</th><th>Type</th><th>Status</th><th>Attempts</th></tr></thead>
<tbody>""" + rows + """</tbody></table></div></section>
<footer>Local snapshot only. No live refresh, job execution, upload or public release.</footer>
</body></html>"""

def main() -> None:
    parser = argparse.ArgumentParser(description="Export private offline owner dashboard HTML")
    parser.add_argument("--db", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    output = Path(args.out).expanduser().resolve()
    if output.suffix.lower() != ".html":
        parser.error("--out must end with .html")
    if output.exists():
        parser.error("Refusing to overwrite an existing dashboard snapshot")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(snapshot(args.db, args.limit)), encoding="utf-8")

if __name__ == "__main__":
    main()
