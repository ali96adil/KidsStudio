"""M66 fake Google crash/restart acceptance tests."""
import tempfile
import unittest
from pathlib import Path
from kidsstudio.m66_fake_google import FakeGoogle, reconcile_known_id, start, state
from kidsstudio.m66_upload_journal_model import JournalError, UNCERTAIN, VERIFIED


class FakeGoogleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal = Path(self.tmp.name) / "journal.json"

    def test_lost_response_blocks_second_insert_after_restart(self):
        fake = FakeGoogle(lose_response=True)
        with self.assertRaises(ConnectionError):
            start(self.journal, fake)
        self.assertEqual(state(self.journal), UNCERTAIN)
        with self.assertRaises(JournalError):
            start(self.journal, fake)
        self.assertEqual(fake.inserts, 1)

    def test_known_id_get_only_reconciliation(self):
        fake = FakeGoogle()
        remote_id = start(self.journal, fake)
        reconcile_known_id(self.journal, fake, remote_id)
        self.assertEqual(state(self.journal), VERIFIED)
        self.assertEqual(fake.inserts, 1)
        with self.assertRaises(JournalError):
            start(self.journal, fake)

    def test_no_known_id_cannot_auto_reconcile(self):
        fake = FakeGoogle(lose_response=True)
        with self.assertRaises(ConnectionError):
            start(self.journal, fake)
        self.assertEqual(state(self.journal), UNCERTAIN)
        self.assertEqual(fake.inserts, 1)

    def test_remote_public_rejected(self):
        fake = FakeGoogle(remote_private=False)
        remote_id = start(self.journal, fake)
        with self.assertRaises(JournalError):
            reconcile_known_id(self.journal, fake, remote_id)
        self.assertEqual(state(self.journal), UNCERTAIN)

    def test_unprocessed_rejected(self):
        fake = FakeGoogle(processed=False)
        remote_id = start(self.journal, fake)
        with self.assertRaises(JournalError):
            reconcile_known_id(self.journal, fake, remote_id)
        self.assertEqual(state(self.journal), UNCERTAIN)

    def test_wrong_id_rejected_without_insert(self):
        fake = FakeGoogle()
        start(self.journal, fake)
        with self.assertRaises(LookupError):
            reconcile_known_id(self.journal, fake, "unknown-id")
        self.assertEqual(fake.inserts, 1)


if __name__ == "__main__":
    unittest.main()
