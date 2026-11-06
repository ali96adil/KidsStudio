import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.episode_notes import EpisodeNotes
from kidsstudio.episode_review_overview import build_episode_review_overview
from kidsstudio.video_review_history import VideoReviewHistory


class EpisodeReviewOverviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "private"
        root.mkdir(mode=0o700)
        self.notes_db = root / "notes.sqlite"
        self.reviews_db = root / "reviews.sqlite"
        notes = EpisodeNotes(self.notes_db)
        notes.initialize()
        notes.add(episode_id="colors_ar_01", text="راجع الصوت")
        self.video = root / "episode.mp4"
        self.video.write_bytes(b"fixture")
        self.sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        history = VideoReviewHistory(self.reviews_db)
        history.initialize()
        history.record(episode_id="colors_ar_01", video_root=str(root),
                       relative_path="episode.mp4", expected_sha256=self.sha,
                       review_outcome="REVISION_REQUIRED")

    def overview(self, sha=None, episode="colors_ar_01"):
        return build_episode_review_overview(
            episode_id=episode, current_video_sha256=sha or self.sha,
            notes_database=str(self.notes_db),
            reviews_database=str(self.reviews_db))

    def test_combines_notes_and_review(self):
        result = self.overview()
        self.assertEqual(result["notes_unresolved"], 1)
        self.assertEqual(result["review_count"], 1)
        self.assertEqual(result["review_freshness"],
                         "CURRENT_VERSION_REVISION_REQUIRED")
        self.assertFalse(result["owner_publication_approval"])

    def test_new_video_marks_review_stale(self):
        result = self.overview(sha="b" * 64)
        self.assertEqual(result["review_freshness"], "LATEST_REVIEW_STALE")

    def test_other_episode_has_no_review(self):
        result = self.overview(episode="colors_en_01")
        self.assertEqual(result["notes_total"], 0)
        self.assertEqual(result["review_count"], 0)
        self.assertEqual(result["review_freshness"], "NO_REVIEW")

    def test_invalid_episode_fails(self):
        with self.assertRaises(ValueError):
            self.overview(episode="../bad")

    def test_invalid_sha_fails(self):
        with self.assertRaises(ValueError):
            self.overview(sha="bad")


if __name__ == "__main__":
    unittest.main()
