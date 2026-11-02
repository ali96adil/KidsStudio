import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_review_store import OwnerReviewStore
from kidsstudio.owner_release_gate import OwnerReleaseGate
from kidsstudio.owner_release_cli import status


class ReleaseCLITests(unittest.TestCase):
    def test_status_tracks_current_review_and_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            reviews = OwnerReviewStore(Path(folder) / "reviews.sqlite")
            gate = OwnerReleaseGate(Path(folder) / "release.sqlite")
            reviews.initialize()
            gate.initialize()
            self.assertFalse(status(reviews, gate, "red")["eligible"])
            reviews.record("red", "approved", "looks good")
            self.assertFalse(status(reviews, gate, "red")["eligible"])
            gate.record("red", "release_authorized", "owner")
            self.assertTrue(status(reviews, gate, "red")["eligible"])
            self.assertFalse(status(reviews, gate, "red")["youtube_visibility_changed"])
            reviews.record("red", "changes_requested", "audio issue")
            self.assertFalse(status(reviews, gate, "red")["eligible"])


if __name__ == "__main__":
    unittest.main()
