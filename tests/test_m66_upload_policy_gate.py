"""M66 fail-closed offline upload policy tests."""
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from kidsstudio.m66_upload_policy_gate import Policy, can_start_private_upload
from kidsstudio.m66_upload_journal_model import begin_insert


class PolicyGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal = Path(self.tmp.name) / "journal.json"
        self.policy = Policy(
            enabled=True, paused=False, revision_requested=False,
            owner_approved_for_private_upload=True, privacy="private",
            daily_limit=3, already_uploaded_today=0,
        )

    def test_valid_private(self):
        self.assertTrue(can_start_private_upload(self.policy, self.journal))

    def test_public_blocked(self):
        self.assertFalse(can_start_private_upload(replace(self.policy, privacy="public"), self.journal))

    def test_paused_blocked(self):
        self.assertFalse(can_start_private_upload(replace(self.policy, paused=True), self.journal))

    def test_revision_blocked(self):
        self.assertFalse(can_start_private_upload(replace(self.policy, revision_requested=True), self.journal))

    def test_owner_approval_missing_blocked(self):
        self.assertFalse(can_start_private_upload(replace(self.policy, owner_approved_for_private_upload=False), self.journal))

    def test_daily_budget_exhausted(self):
        self.assertFalse(can_start_private_upload(replace(self.policy, already_uploaded_today=3), self.journal))

    def test_disabled_blocked(self):
        self.assertFalse(can_start_private_upload(replace(self.policy, enabled=False), self.journal))

    def test_ambiguous_upload_blocked(self):
        begin_insert(self.journal)
        self.assertFalse(can_start_private_upload(self.policy, self.journal))

    def test_corrupt_journal_blocked(self):
        self.journal.write_text("invalid")
        self.assertFalse(can_start_private_upload(self.policy, self.journal))

    def test_negative_budget_blocked(self):
        self.assertFalse(can_start_private_upload(replace(self.policy, already_uploaded_today=-1), self.journal))

    def test_bool_as_integer_blocked(self):
        self.assertFalse(can_start_private_upload(replace(self.policy, daily_limit=True), self.journal))


if __name__ == "__main__":
    unittest.main()
