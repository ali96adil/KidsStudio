import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.video_review_receipt import build_video_review_receipt


class VideoReviewReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "episode.mp4"
        self.video.write_bytes(b"synthetic video fixture")
        self.sha = hashlib.sha256(self.video.read_bytes()).hexdigest()

    def receipt(self, **overrides):
        params = dict(episode_id="colors_ar_01", video_root=str(self.root),
                      relative_path="episode.mp4", expected_sha256=self.sha)
        params.update(overrides)
        return build_video_review_receipt(**params)

    def test_verified_receipt_is_draft_only(self):
        result = self.receipt()
        self.assertEqual(result["video_sha256"], self.sha)
        self.assertEqual(result["video_bytes"], len(self.video.read_bytes()))
        self.assertFalse(result["owner_publication_approval"])
        self.assertFalse(result["receipt_persisted"])

    def test_revision_required_is_not_publication_approval(self):
        result = self.receipt(review_outcome="REVISION_REQUIRED",
                              reviewer_notes="صحح صوت الأرنب")
        self.assertEqual(result["review_outcome"], "REVISION_REQUIRED")
        self.assertFalse(result["publication_performed"])

    def test_accepted_private_does_not_authorize_publication(self):
        result = self.receipt(review_outcome="ACCEPTED_PRIVATE")
        self.assertFalse(result["owner_publication_approval"])

    def test_modified_video_rejected(self):
        self.video.write_bytes(b"changed bytes")
        with self.assertRaises(ValueError):
            self.receipt()

    def test_invalid_episode_rejected(self):
        with self.assertRaises(ValueError):
            self.receipt(episode_id="../other")

    def test_unsafe_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            self.receipt(relative_path="../episode.mp4")

    def test_invalid_review_outcome_rejected(self):
        with self.assertRaises(ValueError):
            self.receipt(review_outcome="PUBLISH")


if __name__ == "__main__":
    unittest.main()
