import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.video_review_history import VideoReviewHistory


class VideoReviewHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.video = self.root / "episode.mp4"
        self.video.write_bytes(b"synthetic version one")
        self.sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.history = VideoReviewHistory(self.root / "reviews.sqlite")
        self.history.initialize()

    def record(self, **kwargs):
        params = dict(episode_id="colors_ar_01", video_root=str(self.root),
                      relative_path="episode.mp4", expected_sha256=self.sha)
        params.update(kwargs)
        return self.history.record(**params)

    def test_record_and_list(self):
        result = self.record(reviewer_notes="راجع الصوت")
        self.assertFalse(result["owner_publication_approval"])
        reviews = self.history.list_reviews(episode_id="colors_ar_01")
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["video_sha256"], self.sha)

    def test_multiple_versions_preserved(self):
        self.record(review_outcome="REVISION_REQUIRED")
        self.video.write_bytes(b"synthetic version two")
        new_sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.record(expected_sha256=new_sha, review_outcome="ACCEPTED_PRIVATE")
        reviews = self.history.list_reviews(episode_id="colors_ar_01")
        self.assertEqual([r["video_sha256"] for r in reviews], [self.sha, new_sha])
        self.assertFalse(reviews[1]["owner_publication_approval"])

    def test_tampered_video_not_recorded(self):
        self.video.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.record()
        self.assertEqual(self.history.list_reviews(episode_id="colors_ar_01"), [])

    def test_episode_isolation(self):
        self.record()
        self.assertEqual(self.history.list_reviews(episode_id="colors_en_01"), [])

    def test_invalid_episode_rejected(self):
        with self.assertRaises(ValueError):
            self.record(episode_id="../bad")

    def test_existing_history_not_overwritten(self):
        with self.assertRaises(FileExistsError):
            self.history.initialize()

    def test_unapproved_even_if_private_accepted(self):
        self.record(review_outcome="ACCEPTED_PRIVATE")
        self.assertFalse(self.history.list_reviews(episode_id="colors_ar_01")[0][
            "owner_publication_approval"])


if __name__ == "__main__":
    unittest.main()
