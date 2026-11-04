"""Offline M66 fail-closed restart journal tests."""
import tempfile
import unittest
from pathlib import Path
from kidsstudio.m66_upload_journal_model import (
    JournalError, begin_insert, may_insert, read, verified_private,
    UNCERTAIN, VERIFIED,
)


class UploadJournalModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "upload.json"

    def test_new_may_insert(self):
        self.assertTrue(may_insert(self.path))

    def test_restart_after_begin_denies_second_insert(self):
        begin_insert(self.path)
        self.assertFalse(may_insert(self.path))
        self.assertEqual(read(self.path)["state"], UNCERTAIN)
        with self.assertRaises(JournalError):
            begin_insert(self.path)

    def test_verified_private_still_denies_insert(self):
        begin_insert(self.path)
        verified_private(self.path, "synthetic-id", remote_private=True, processed=True)
        self.assertEqual(read(self.path)["state"], VERIFIED)
        self.assertFalse(may_insert(self.path))

    def test_public_denied(self):
        begin_insert(self.path)
        with self.assertRaises(JournalError):
            verified_private(self.path, "id", remote_private=False, processed=True)

    def test_unprocessed_denied(self):
        begin_insert(self.path)
        with self.assertRaises(JournalError):
            verified_private(self.path, "id", remote_private=True, processed=False)

    def test_corrupt_journal_denies_insert(self):
        self.path.write_text("{bad")
        with self.assertRaises(JournalError):
            may_insert(self.path)

    def test_symlink_denied(self):
        target = Path(self.tmp.name) / "target"
        target.write_text("irrelevant")
        self.path.symlink_to(target)
        with self.assertRaises(JournalError):
            may_insert(self.path)


if __name__ == "__main__":
    unittest.main()
