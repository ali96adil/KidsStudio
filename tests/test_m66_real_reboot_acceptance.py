"""M66 end-to-end offline reboot acceptance for real SQLite journal.

No mock reports: create actual upload attempts, take two read-only snapshots,
then compare using the same code the Pi operator runs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m66_journal_report import inspect_journal
from kidsstudio.m66_reboot_compare import compare
from kidsstudio.youtube_private_upload import UploadJournal


class RealRebootAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "upload.sqlite"
        self.journal = UploadJournal(self.path)

    def test_reopen_without_changes_is_stable(self):
        job = "a" * 32
        self.journal.reserve(job, "b" * 64, "c" * 64)
        before = inspect_journal(self.path)
        self.assertEqual(UploadJournal(self.path).status(job)["state"], "STARTED")
        after = inspect_journal(self.path)
        self.assertTrue(compare(before, after)["pass"])

    def test_same_state_counts_but_changed_plan_is_detected(self):
        job = "a" * 32
        self.journal.reserve(job, "b" * 64, "c" * 64)
        before = inspect_journal(self.path)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE attempts SET plan_sha256=? WHERE render_job_id=?",
                       ("d" * 64, job))
        after = inspect_journal(self.path)
        self.assertEqual(before["states"], after["states"])
        self.assertFalse(compare(before, after)["pass"])

    def test_state_transition_is_detected(self):
        job = "a" * 32
        self.journal.reserve(job, "b" * 64, "c" * 64)
        before = inspect_journal(self.path)
        self.journal.record_uploaded(job, "AbCdef12345")
        after = inspect_journal(self.path)
        self.assertFalse(compare(before, after)["pass"])

    def test_report_does_not_change_sqlite_contents(self):
        job = "a" * 32
        self.journal.reserve(job, "b" * 64, "c" * 64)
        with sqlite3.connect(self.path) as db:
            before = db.execute("SELECT * FROM attempts").fetchall()
            changes_before = db.total_changes
        inspect_journal(self.path)
        inspect_journal(self.path)
        with sqlite3.connect(self.path) as db:
            after = db.execute("SELECT * FROM attempts").fetchall()
            changes_after = db.total_changes
        self.assertEqual(before, after)
        self.assertEqual(changes_before, changes_after)


if __name__ == "__main__":
    unittest.main()
