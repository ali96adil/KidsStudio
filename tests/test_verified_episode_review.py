import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.episode_notes import EpisodeNotes
from kidsstudio.video_review_history import VideoReviewHistory
from kidsstudio.verified_episode_review import build_verified_episode_review


class VerifiedEpisodeReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.video = self.root / "video.mp4"
        self.video.write_bytes(b"first version")
        self.sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.notes_db = self.root / "notes.sqlite"
        self.reviews_db = self.root / "reviews.sqlite"
        notes = EpisodeNotes(self.notes_db)
        notes.initialize()
        notes.add(episode_id="colors_ar_01", text="راجع الصوت")
        history = VideoReviewHistory(self.reviews_db)
        history.initialize()
        history.record(episode_id="colors_ar_01", video_root=str(self.root),
                       relative_path="video.mp4", expected_sha256=self.sha,
                       review_outcome="ACCEPTED_PRIVATE")

    def report(self, sha=None):
        return build_verified_episode_review(
            episode_id="colors_ar_01", video_root=str(self.root),
            relative_path="video.mp4", expected_sha256=sha or self.sha,
            notes_database=str(self.notes_db),
            reviews_database=str(self.reviews_db))

    def test_verified_current_version(self):
        result = self.report()
        self.assertEqual(result["status"], "EPISODE_REVIEW_LOCAL_VIDEO_VERIFIED")
        self.assertEqual(result["review_freshness"], "CURRENT_VERSION_ACCEPTED_PRIVATE_ONLY")
        self.assertTrue(result["local_file_verified_at_report_time"])
        self.assertFalse(result["owner_publication_approval"])

    def test_changed_video_fails_closed(self):
        self.video.write_bytes(b"changed video")
        with self.assertRaises(ValueError):
            self.report()

    def test_wrong_expected_sha_fails_closed(self):
        with self.assertRaises(ValueError):
            self.report("b" * 64)

    def test_new_verified_version_marks_old_review_stale(self):
        self.video.write_bytes(b"new version")
        sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        result = self.report(sha)
        self.assertEqual(result["review_freshness"], "LATEST_REVIEW_STALE")

    def test_traversal_fails_closed(self):
        with self.assertRaises(ValueError):
            build_verified_episode_review(
                episode_id="colors_ar_01", video_root=str(self.root),
                relative_path="../outside.mp4", expected_sha256=self.sha,
                notes_database=str(self.notes_db),
                reviews_database=str(self.reviews_db))


if __name__ == "__main__":
    unittest.main()
