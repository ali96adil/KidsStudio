"""M66 integration tests combining policy, journal, fake transport."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m66_guarded_uploader import attempt_private_upload, reconcile_private_upload
from kidsstudio.m66_fake_google import FakeGoogle
from kidsstudio.m66_upload_journal_model import JournalError, read, UNCERTAIN, VERIFIED
from kidsstudio.m66_upload_policy_gate import Policy


class GuardedUploaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "upload.json"
        self.policy = Policy(
            enabled=True, paused=False, revision_requested=False,
            owner_approved_for_private_upload=True, privacy="private",
            daily_limit=2, already_uploaded_today=0,
        )

    def test_happy_path_private_reconcile(self):
        fake = FakeGoogle()
        video_id = attempt_private_upload(self.policy, self.path, fake)
        self.assertEqual(reconcile_private_upload(self.path, fake, video_id), VERIFIED)
        self.assertEqual(fake.inserts, 1)

    def test_response_lost_and_restart_no_duplicate(self):
        fake = FakeGoogle(lose_response=True)
        with self.assertRaises(ConnectionError):
            attempt_private_upload(self.policy, self.path, fake)
        self.assertEqual(read(self.path)["state"], UNCERTAIN)
        with self.assertRaises(JournalError):
            attempt_private_upload(self.policy, self.path, fake)
        self.assertEqual(fake.inserts, 1)

    def test_policy_paused_before_insert(self):
        fake = FakeGoogle()
        with self.assertRaises(JournalError):
            attempt_private_upload(replace(self.policy, paused=True), self.path, fake)
        self.assertEqual(fake.inserts, 0)

    def test_budget_exhausted_before_insert(self):
        fake = FakeGoogle()
        with self.assertRaises(JournalError):
            attempt_private_upload(replace(self.policy, already_uploaded_today=2), self.path, fake)
        self.assertEqual(fake.inserts, 0)

    def test_public_before_insert(self):
        fake = FakeGoogle()
        with self.assertRaises(JournalError):
            attempt_private_upload(replace(self.policy, privacy="public"), self.path, fake)
        self.assertEqual(fake.inserts, 0)

    def test_revisions_before_insert(self):
        fake = FakeGoogle()
        with self.assertRaises(JournalError):
            attempt_private_upload(replace(self.policy, revision_requested=True), self.path, fake)
        self.assertEqual(fake.inserts, 0)

    def test_unverified_remote_never_finalized(self):
        fake = FakeGoogle(remote_private=False)
        video_id = attempt_private_upload(self.policy, self.path, fake)
        with self.assertRaises(JournalError):
            reconcile_private_upload(self.path, fake, video_id)
        self.assertEqual(read(self.path)["state"], UNCERTAIN)


if __name__ == "__main__":
    unittest.main()
