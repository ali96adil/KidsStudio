import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.owner_review_store import OwnerReviewStore
from kidsstudio.owner_release_gate import OwnerReleaseGate
from kidsstudio.youtube_release_inspection import inspect_release
from kidsstudio.youtube_video_inspector import YouTubeInspectError


class ReleaseInspectionTests(unittest.TestCase):
    def test_channel_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            reviews = OwnerReviewStore(Path(root) / "reviews.db")
            gate = OwnerReleaseGate(Path(root) / "gate.db")
            reviews.initialize()
            gate.initialize()
            with patch("kidsstudio.youtube_release_inspection.inspect_video",
                       return_value={"channel_id": "wrong", "privacy": "private"}):
                with self.assertRaises(YouTubeInspectError):
                    inspect_release(reviews, gate, "red", "Abc123_defG", "expected", "token")

    def test_matching_channel_still_requires_owner_approval(self):
        with tempfile.TemporaryDirectory() as root:
            reviews = OwnerReviewStore(Path(root) / "reviews.db")
            gate = OwnerReleaseGate(Path(root) / "gate.db")
            reviews.initialize()
            gate.initialize()
            with patch("kidsstudio.youtube_release_inspection.inspect_video",
                       return_value={"channel_id": "expected", "privacy": "private"}):
                result = inspect_release(reviews, gate, "red", "Abc123_defG", "expected", "token")
            self.assertFalse(result["ready_for_manual_release"])
            self.assertTrue(result["channel_id_verified"])
            self.assertFalse(result["youtube_request_sent"])


if __name__ == "__main__":
    unittest.main()
