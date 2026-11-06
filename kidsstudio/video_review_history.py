"""Private append-only local video review history.

Stores metadata receipts only; not an owner authentication or publishing system.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import time

from .video_review_receipt import build_video_review_receipt

_EPISODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


class VideoReviewHistory:
    def __init__(self, database: str | Path):
        self.path = Path(database).expanduser().resolve()
        if self.path.suffix not in {".db", ".sqlite"}:
            raise ValueError("invalid review database")
        if any((parent / ".git").exists() for parent in (self.path.parent, *self.path.parents)):
            raise ValueError("review history must remain outside Git")

    def initialize(self) -> None:
        if self.path.exists():
            raise FileExistsError("review history already exists")
        if not self.path.parent.is_dir() or self.path.parent.stat().st_mode & 0o077:
            raise ValueError("existing private directory required")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        try:
            with sqlite3.connect(self.path) as db:
                db.executescript("""
                    CREATE TABLE reviews (
                        review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        episode_id TEXT NOT NULL,
                        video_sha256 TEXT NOT NULL,
                        video_bytes INTEGER NOT NULL,
                        outcome TEXT NOT NULL,
                        reviewer_notes TEXT NOT NULL,
                        recorded_at REAL NOT NULL
                    );
                    CREATE INDEX review_episode ON reviews(episode_id,review_id);
                """)
        except Exception:
            self.path.unlink(missing_ok=True)
            raise

    def _connect(self, *, readonly: bool = False):
        if not self.path.is_file():
            raise ValueError("review history not initialized")
        if readonly:
            return sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        return sqlite3.connect(self.path)

    def record(self, *, episode_id: str, video_root: str, relative_path: str,
               expected_sha256: str, reviewer_notes: str = "",
               review_outcome: str = "NEEDS_REVIEW") -> dict:
        receipt = build_video_review_receipt(
            episode_id=episode_id, video_root=video_root,
            relative_path=relative_path, expected_sha256=expected_sha256,
            reviewer_notes=reviewer_notes, review_outcome=review_outcome)
        with self._connect() as db:
            cur = db.execute(
                "INSERT INTO reviews(episode_id,video_sha256,video_bytes,outcome,"
                "reviewer_notes,recorded_at) VALUES(?,?,?,?,?,?)",
                (receipt["episode_id"], receipt["video_sha256"],
                 receipt["video_bytes"], receipt["review_outcome"],
                 receipt["reviewer_notes"], time.time()))
            review_id = int(cur.lastrowid)
        return {"status": "REVIEW_RECORDED", "review_id": review_id,
                "episode_id": episode_id, "video_sha256": receipt["video_sha256"],
                "owner_publication_approval": False,
                "reviewer_identity_authenticated": False}

    def list_reviews(self, *, episode_id: str) -> list[dict]:
        if not isinstance(episode_id, str) or not _EPISODE.fullmatch(episode_id):
            raise ValueError("invalid episode id")
        with self._connect(readonly=True) as db:
            rows = db.execute(
                "SELECT review_id,video_sha256,video_bytes,outcome,reviewer_notes,"
                "recorded_at FROM reviews WHERE episode_id=? ORDER BY review_id",
                (episode_id,)).fetchall()
        return [{"review_id": rid, "video_sha256": sha, "video_bytes": size,
                 "review_outcome": outcome, "reviewer_notes": notes,
                 "recorded_at": recorded, "owner_publication_approval": False}
                for rid, sha, size, outcome, notes, recorded in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private local video review history")
    parser.add_argument("--db", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    record = sub.add_parser("record")
    record.add_argument("--episode-id", required=True)
    record.add_argument("--video-root", required=True)
    record.add_argument("--relative-path", required=True)
    record.add_argument("--expected-sha256", required=True)
    record.add_argument("--reviewer-notes", default="")
    record.add_argument("--review-outcome", default="NEEDS_REVIEW",
                        choices=["NEEDS_REVIEW", "REVISION_REQUIRED", "ACCEPTED_PRIVATE"])
    show = sub.add_parser("list")
    show.add_argument("--episode-id", required=True)
    args = parser.parse_args(argv)
    try:
        history = VideoReviewHistory(args.db)
        if args.action == "init":
            history.initialize()
            result = {"status": "INITIALIZED"}
        elif args.action == "record":
            result = history.record(
                episode_id=args.episode_id, video_root=args.video_root,
                relative_path=args.relative_path, expected_sha256=args.expected_sha256,
                reviewer_notes=args.reviewer_notes, review_outcome=args.review_outcome)
        else:
            result = {"status": "REVIEWS_READ_ONLY", "reviews": history.list_reviews(
                episode_id=args.episode_id)}
    except (ValueError, OSError, sqlite3.Error):
        print(json.dumps({"status": "REVIEW_HISTORY_ERROR",
                          "owner_publication_approval": False}))
        return 2
    result["owner_publication_approval"] = False
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
