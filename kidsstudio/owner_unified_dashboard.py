"""Offline owner overview combining production and Pi private-upload health.

The export is read-only; it never contacts YouTube or changes visibility.
"""
from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from .owner_dashboard_combined import render_combined
from .owner_dashboard_snapshot import snapshot
from .owner_series_board import load as load_series
from .owner_review_store import OwnerReviewStore
from .pi_upload_dashboard import upload_snapshot
from .pi_upload_queue import PiUploadQueue
from .owner_episode_status import episode_statuses


def render_unified(production: dict, series: dict, reviews: dict,
                   uploads: dict, episodes: list[dict] | None = None) -> str:
    html = render_combined(production, series, reviews)
    counts = uploads["queue"]
    sessions = uploads["sessions"]["counts"]
    metrics = (
        ("Waiting", counts["pending"]),
        ("Uploading", counts["running"]),
        ("Uploaded", counts["completed"]),
        ("Upload failures", counts["failed"]),
        ("Corrupt sessions", sessions["corrupt"]),
        ("Orphaned sessions", sessions["orphaned"]),
        ("Invalid referenced sessions", sessions.get("invalid_referenced", 0)),
        ("Missing sessions", sessions.get("missing", 0)),
        ("Session intents to review", uploads.get("session_intents", {}).get("pending_reconciliation", 0)),
        ("Invalid session intents", uploads.get("session_intents", {}).get("invalid_intents", 0)),
        ("Sessions requiring review", sum(
            1 for item in uploads.get("reconciliation", {}).get("episodes", [])
            if item["action"] == "manual_reconcile_youtube_before_retry"
        )),
    )
    cards = "".join(
        '<div class="metric"><span>' + escape(label) + '</span><strong>' +
        str(int(value)) + '</strong></div>' for label, value in metrics
    )
    section = (
        '<section aria-label="Private YouTube uploads">'
        '<h2>Private YouTube uploads</h2>'
        '<p>Read-only Pi status; completed means private upload only, not public release.</p>'
        '<div class="metrics">' + cards + '</div></section>'
    )
    if episodes is not None:
        rows = "".join(
            "<tr>" + "".join("<td>" + escape(str(item[key])) + "</td>"
            for key in ("series", "title", "production_stage", "review_state", "upload_state", "next_step")) + "</tr>"
            for item in episodes
        )
        section += (
            '<section aria-label="Episode progress"><h2>Episode progress</h2>'
            '<div class="table-wrap"><table><thead><tr><th>Series</th><th>Episode</th>'
            '<th>Production</th><th>Review</th><th>Private upload</th><th>Next step</th>'
            '</tr></thead><tbody>' + (rows or '<tr><td colspan="6">No episodes yet</td></tr>') +
            '</tbody></table></div></section>'
        )
    marker = "<footer>Local snapshot only."
    if marker not in html:
        raise ValueError("owner dashboard template marker missing")
    return html.replace(marker, section + marker, 1)


def export_unified(*, production_db: str | Path, series_file: str | Path,
                   review_db: str | Path, pi_state_dir: str | Path,
                   output: str | Path, limit: int = 25) -> Path:
    dest = Path(output)
    if dest.suffix.lower() != ".html" or dest.exists() or dest.is_symlink():
        raise ValueError("output must be a new HTML file")
    pi = Path(pi_state_dir)
    series_data = load_series(series_file)
    reviews = OwnerReviewStore(review_db).latest()
    page = render_unified(
        snapshot(production_db, limit), series_data, reviews,
        upload_snapshot(PiUploadQueue(pi / "queue.sqlite"), pi / "sessions"),
        episode_statuses(series_data, reviews, pi / "queue.sqlite"),
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("x", encoding="utf-8") as stream:
        stream.write(page)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export unified offline owner overview")
    parser.add_argument("--production-db", required=True)
    parser.add_argument("--series", required=True)
    parser.add_argument("--review-db", required=True)
    parser.add_argument("--pi-state-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    export_unified(production_db=args.production_db, series_file=args.series,
                   review_db=args.review_db, pi_state_dir=args.pi_state_dir,
                   output=args.out, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
