"""Private, read-only HTML dashboard for Pi upload queue and session health."""
from __future__ import annotations

import argparse
import sqlite3
from html import escape
from pathlib import Path

from .pi_upload_queue import PiUploadQueue
from .pi_upload_session_audit import audit_sessions

STATES = ("pending", "running", "completed", "failed")


def upload_snapshot(queue: PiUploadQueue, session_dir: str | Path) -> dict:
    with sqlite3.connect(queue.path, timeout=10) as db:
        rows = db.execute(
            "SELECT state,COUNT(*) FROM pi_upload_jobs GROUP BY state"
        ).fetchall()
    counts = {state: 0 for state in STATES}
    for state, count in rows:
        if state in counts:
            counts[state] = int(count)
    return {"read_only": True, "queue": counts,
            "sessions": audit_sessions(queue, session_dir)}


def render_upload_dashboard(data: dict) -> str:
    queue = data["queue"]
    audit = data["sessions"]
    metrics = [
        ("Waiting", queue["pending"]), ("Uploading", queue["running"]),
        ("Completed", queue["completed"]), ("Failed", queue["failed"]),
        ("Corrupt sessions", audit["counts"]["corrupt"]),
        ("Orphaned sessions", audit["counts"]["orphaned"]),
        ("Missing sessions", audit["counts"].get("missing", 0)),
    ]
    cards = "".join(
        '<div class="metric"><span>' + escape(label) + '</span><strong>' +
        str(int(value)) + '</strong></div>'
        for label, value in metrics
    )
    status = "Attention required" if queue["failed"] or not audit["healthy"] else "No detected upload issues"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;">'
        '<title>Kids Studio | Private uploads</title><style>'
        'body{font-family:system-ui,sans-serif;max-width:950px;margin:2rem auto;padding:0 1rem}'
        '.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem}'
        '.metric{border:1px solid #8888;border-radius:12px;padding:1rem}'
        '.metric span{display:block}.metric strong{font-size:2rem}'
        '</style></head><body><h1>Kids Studio · Private uploads</h1>'
        '<p>Read-only offline snapshot · no live network access</p>'
        '<section class="metrics">' + cards + '</section><h2>' + escape(status) +
        '</h2><p>Sessions checked locally. No upload or release action is available.</p>'
        '</body></html>'
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export read-only Pi upload dashboard")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    if output.suffix.lower() != ".html" or output.exists() or output.is_symlink():
        parser.error("output must be a new HTML file")
    state = Path(args.state_dir)
    queue = PiUploadQueue(state / "queue.sqlite")
    page = render_upload_dashboard(upload_snapshot(queue, state / "sessions"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
