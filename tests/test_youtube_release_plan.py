import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_release_gate import OwnerReleaseGate
from kidsstudio.owner_review_store import OwnerReviewStore
from kidsstudio.youtube_release_plan import plan_visibility_change


class YouTubeReleasePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reviews = OwnerReviewStore(Path(self.tmp.name) / "reviews.db")
        self.gate = OwnerReleaseGate(Path(self.tmp.name) / "release.db")
        self.reviews.initialize()
        self.gate.initialize()
        self.video_id = "Abc123_defG"

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, privacy="private"):
        return plan_visibility_change(self.reviews, self.gate, "red-ar", self.video_id, privacy)

    def test_default_denied(self):
        result = self.plan()
        self.assertFalse(result["ready_for_manual_release"])
        self.assertIsNone(result["requested_privacy"])

    def test_two_approvals_required(self):
        self.reviews.record(episode_id="red-ar", state="approved", note="ok")
        self.assertFalse(self.plan()["ready_for_manual_release"])
        self.gate.record("red-ar", "release_authorized", "owner")
        result = self.plan()
        self.assertTrue(result["ready_for_manual_release"])
        self.assertEqual(result["requested_privacy"], "public")
        self.assertFalse(result["youtube_request_sent"])

    def test_revoke_and_non_private_denied(self):
        self.reviews.record(episode_id="red-ar", state="approved", note="ok")
        self.gate.record("red-ar", "release_authorized", "owner")
        self.assertFalse(self.plan("unlisted")["ready_for_manual_release"])
        self.assertFalse(self.plan("public")["ready_for_manual_release"])
        self.gate.record("red-ar", "hold", "owner")
        self.assertFalse(self.plan()["ready_for_manual_release"])

    def test_invalid_id(self):
        with self.assertRaises(ValueError):
            plan_visibility_change(self.reviews, self.gate, "red-ar", "not-an-id", "private")


if __name__ == "__main__":
    unittest.main()
