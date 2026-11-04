"""Tests for M68 shared private-upload budget precheck."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.studio_queue import StudioQueue
from kidsstudio.m68_short_budget import assess_short_budget


class ShortBudgetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.queue = StudioQueue(Path(tmp.name) / "queue.sqlite",
                                 clock=lambda: 1000000)
        self.queue.initialize()
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY,max_uploads_24h INTEGER)""")
            db.execute("INSERT INTO studio_youtube_private_policies VALUES('colors',2)")
        self.kwargs = dict(short_id="colors-short-01",
                           source_episode_id="colors-ep-01",
                           media_sha256="a" * 64, series_id="colors",
                           channel_id="UC1234567890123456789012",
                           made_for_kids=True,
                           contains_synthetic_media=True)

    def check(self):
        with patch("kidsstudio.m68_short_budget.assess_short_policy",
                   return_value={"reasons": []}):
            return assess_short_budget(self.queue, **self.kwargs)

    def add_upload(self, state, created_at, job_id):
        with self.queue._connection(write=True) as db:
            db.execute("""INSERT INTO jobs(
                job_id,request_key,kind,payload,state,max_attempts,
                available_at,created_at,updated_at)
                VALUES (?,?,?,?,?,1,?,?,?)""",
                (job_id, job_id, "youtube_private_upload",
                 json.dumps({"series_id": "colors"}), state,
                 created_at, created_at, created_at))

    def test_empty_budget_is_not_upload_authorization(self):
        result = self.check()
        self.assertEqual(result["status"],
                         "SHORT_BUDGET_PRECHECK_PASSED_UPLOAD_STILL_BLOCKED")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_shared_daily_budget_blocks(self):
        self.add_upload("COMPLETED", 999999, "a" * 32)
        self.add_upload("COMPLETED", 999998, "b" * 32)
        self.assertIn("SHARED_24H_PRIVATE_UPLOAD_BUDGET_EXHAUSTED",
                      self.check()["reasons"])

    def test_active_upload_blocks(self):
        self.add_upload("LEASED", 900000, "a" * 32)
        self.assertIn("ANOTHER_PRIVATE_UPLOAD_IN_FLIGHT",
                      self.check()["reasons"])

    def test_old_completed_upload_does_not_use_daily_budget(self):
        self.add_upload("COMPLETED", 800000, "a" * 32)
        self.assertEqual(self.check()["recent_upload_jobs"], 0)
