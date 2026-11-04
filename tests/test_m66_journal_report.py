"""M66 read-only report against real upload journal."""
import contextlib
import io
import sqlite3
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m66_journal_report import inspect_journal, main
from kidsstudio.youtube_private_upload import UploadJournal


class JournalReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "upload.sqlite"
        self.journal = UploadJournal(self.path)

    def test_empty_report(self):
        report = inspect_journal(self.path)
        self.assertEqual(report["total"], 0)
        self.assertFalse(report["network_used"])

    def test_uncertain_state_reported_after_restart(self):
        job = "a" * 32
        self.journal.reserve(job, "b" * 64, "c" * 64)
        report = inspect_journal(self.path)
        self.assertEqual(report["states"]["STARTED"], 1)
        self.assertEqual(report["requires_manual_reconciliation"], [job])
        self.assertEqual(UploadJournal(self.path).status(job)["state"], "STARTED")

    def test_verified_is_not_uncertain(self):
        job = "a" * 32
        self.journal.reserve(job, "b" * 64, "c" * 64)
        self.journal.record_uploaded(job, "AbCdef12345")
        self.journal.record_verified(job, "AbCdef12345")
        report = inspect_journal(self.path)
        self.assertEqual(report["states"]["PRIVATE_VERIFIED"], 1)
        self.assertEqual(report["requires_manual_reconciliation"], [])

    def test_missing_file_fails_closed_without_creating_it(self):
        missing = Path(self.temp.name) / "missing.sqlite"
        with self.assertRaises(ValueError):
            inspect_journal(missing)
        self.assertFalse(missing.exists())

    def test_symlink_rejected(self):
        link = Path(self.temp.name) / "linked.sqlite"
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            inspect_journal(link)

    def test_cli_report(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--journal", str(self.path)]), 0)
        self.assertIn("M66_READ_ONLY_JOURNAL_REPORT", out.getvalue())


if __name__ == "__main__":
    unittest.main()
