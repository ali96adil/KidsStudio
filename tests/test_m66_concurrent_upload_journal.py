"""M66 concurrency acceptance tests for actual M25/M65 SQLite journal.

Synthetic records only; no network, YouTube, Pi or OAuth. Concurrent reserve
must allow one winner and reject all duplicate jobs and master SHA values.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from kidsstudio.youtube_private_upload import UploadJournal, YouTubePrivateError


class ConcurrentJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "journal.sqlite"
        UploadJournal(self.path)
        self.job = "a" * 32
        self.sha = "b" * 64
        self.plan = "c" * 64

    def test_concurrent_same_job_only_one_reservation(self):
        def reserve(_):
            try:
                UploadJournal(self.path).reserve(self.job, self.sha, self.plan)
                return "reserved"
            except YouTubePrivateError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(results.count("reserved"), 1)
        self.assertEqual(results.count("blocked"), 7)
        self.assertEqual(UploadJournal(self.path).status(self.job)["state"], "STARTED")

    def test_concurrent_distinct_jobs_same_master_only_one(self):
        def reserve(i):
            job = f"{i:032x}"
            try:
                UploadJournal(self.path).reserve(job, self.sha, self.plan)
                return "reserved"
            except YouTubePrivateError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(results.count("reserved"), 1)
        self.assertEqual(results.count("blocked"), 7)


if __name__ == "__main__":
    unittest.main()
