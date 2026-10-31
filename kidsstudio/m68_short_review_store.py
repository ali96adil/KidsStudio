"""Durable M68 derived-short review evidence, separate from M65 episodes.

A PASS records content review only. It cannot authorize a YouTube upload.
"""
from __future__ import annotations

import json

from .m68_short_content_review import CHECKS


class ShortReviewStoreError(ValueError):
    pass


class ShortReviewStore:
    def __init__(self, queue):
        self.queue = queue

    def initialize(self):
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_short_reviews (
                short_id TEXT PRIMARY KEY,
                source_episode_id TEXT NOT NULL,
                media_sha256 TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('PASS','REJECT')),
                reviewer TEXT NOT NULL,
                checks_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(short_id) REFERENCES studio_derived_shorts(short_id)
            )""")

    def record(self, receipt):
        if not isinstance(receipt, dict):
            raise ShortReviewStoreError("review receipt required")
        checks = receipt.get("checks")
        if (receipt.get("status") != "SHORT_CONTENT_QA_RECORDED"
                or receipt.get("decision") not in ("PASS", "REJECT")
                or not isinstance(checks, dict) or set(checks) != set(CHECKS)
                or any(type(checks[key]) is not bool for key in CHECKS)
                or (receipt["decision"] == "PASS") != all(checks.values())
                or not isinstance(receipt.get("reviewer"), str)
                or not 3 <= len(receipt["reviewer"].strip()) <= 100
                or receipt.get("youtube_upload_authorized") is not False
                or receipt.get("public_release_authorized") is not False):
            raise ShortReviewStoreError("invalid independent content review")
        with self.queue._connection(write=True) as db:
            short = db.execute(
                "SELECT * FROM studio_derived_shorts WHERE short_id=?",
                (receipt.get("short_id"),)).fetchone()
            if (not short or short["state"] != "PI_STAGED_NOT_APPROVED"
                    or short["source_episode_id"] != receipt.get("source_episode_id")
                    or short["media_sha256"] != receipt.get("video_sha256")):
                raise ShortReviewStoreError("review does not match staged short")
            # AI receipts must carry independently recorded six-axis evidence.
            # Legacy explicit reviews remain valid; this does not claim that
            # arbitrary reviewer strings are proof of model execution.
            if receipt.get("ai_review_completed") is True:
                evidence = receipt.get("ai_evidence")
                if (receipt.get("ai_evidence_video_sha256") != short["media_sha256"]
                        or not isinstance(evidence, dict)
                        or set(evidence) != set(CHECKS)
                        or any(not isinstance(evidence[k], str)
                               or not 12 <= len(evidence[k].strip()) <= 2000
                               for k in CHECKS)):
                    raise ShortReviewStoreError("AI review evidence missing or mismatched")
            if receipt.get("ai_review_completed") not in (None, True):
                raise ShortReviewStoreError("invalid AI completion marker")
            if receipt.get("ai_evidence") is not None and receipt.get("ai_review_completed") is not True:
                raise ShortReviewStoreError("unverified AI evidence marker")
            packed = json.dumps(checks, sort_keys=True)
            prior = db.execute(
                "SELECT * FROM studio_short_reviews WHERE short_id=?",
                (receipt["short_id"],)).fetchone()
            if prior:
                if (prior["source_episode_id"] != short["source_episode_id"]
                        or prior["media_sha256"] != short["media_sha256"]
                        or prior["decision"] != receipt["decision"]
                        or prior["reviewer"] != receipt["reviewer"]
                        or prior["checks_json"] != packed):
                    raise ShortReviewStoreError("review already recorded; cannot overwrite")
                return self._report(prior)
            db.execute("""INSERT INTO studio_short_reviews
                (short_id,source_episode_id,media_sha256,decision,
                 reviewer,checks_json,created_at) VALUES (?,?,?,?,?,?,?)""",
                (short["short_id"], short["source_episode_id"],
                 short["media_sha256"], receipt["decision"],
                 receipt["reviewer"], packed, self.queue.clock()))
            return self._report(db.execute(
                "SELECT * FROM studio_short_reviews WHERE short_id=?",
                (receipt["short_id"],)).fetchone())

    @staticmethod
    def _report(row):
        return {
            "short_id": row["short_id"],
            "source_episode_id": row["source_episode_id"],
            "media_sha256": row["media_sha256"],
            "decision": row["decision"],
            "reviewer": row["reviewer"],
            "status": "SHORT_CONTENT_REVIEW_RECORDED_NOT_UPLOAD_APPROVED",
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }
