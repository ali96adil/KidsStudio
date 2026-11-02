"""Combined offline owner view: job queue + educational series progress."""
from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from .owner_dashboard_html import render as render_queue
from .owner_dashboard_snapshot import snapshot
from .owner_series_board import load as load_series
from .owner_video_reviews import latest_reviews, read_journal

def render_combined(queue_data: dict, series_data: dict, reviews: dict | None = None) -> str:
    """Insert escaped series summary into the local read-only queue dashboard."""
    html = render_queue(queue_data)
    reviews = reviews or {}
    blocks = []
    for series in series_data["series"]:
        counts = ", ".join(
            f"{escape(stage)}: {int(count)}"
            for stage, count in series["stage_counts"].items() if count
        ) or "No episodes"
        rows = "".join(
            "<li>" + escape(ep["title"]) + " — " + escape(ep["stage"]) +
            " · owner: " + escape(reviews.get(ep["id"], {}).get("state", "needs_review")) + "</li>"
            for ep in series["episodes"]
        )
        blocks.append(
            "<article><h3>" + escape(series["title"]) + "</h3>"
            "<p>Episodes: " + str(int(series["episode_count"])) + "</p>"
            "<p>" + counts + "</p><ul>" + rows + "</ul></article>"
        )
    section = (
        '<section aria-label="Educational series"><h2>Educational series</h2>'
        '<p>Total episodes: ' + str(int(series_data["episode_count"])) + '</p>' +
        ("".join(blocks) or "<p>No series planned yet</p>") + "</section>"
    )
    marker = "<footer>Local snapshot only."
    if marker not in html:
        raise ValueError("Dashboard template marker missing")
    return html.replace(marker, section + marker, 1)

def main() -> None:
    parser = argparse.ArgumentParser(description="Export local owner overview with series")
    parser.add_argument("--db", required=True)
    parser.add_argument("--series", required=True, help="Local JSON series manifest")
    parser.add_argument("--reviews", help="Optional local owner review journal")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    output = Path(args.out).expanduser().resolve()
    if output.suffix.lower() != ".html" or output.exists():
        parser.error("--out must be a new .html path")
    reviews = latest_reviews(read_journal(args.reviews)) if args.reviews else {}
    page = render_combined(snapshot(args.db, args.limit), load_series(args.series), reviews)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")

if __name__ == "__main__":
    main()
