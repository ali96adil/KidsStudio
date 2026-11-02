import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_video_reviews import append_review, latest_reviews, read_journal


class OwnerVideoReviewTests(unittest.TestCase):
    def test_review_history_and_latest_state(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "reviews.json"
            append_review(path, episode_id="red-ar", state="changes_requested", note="أصلح الصوت")
            append_review(path, episode_id="red-ar", state="approved", note="جاهز للمراجعة النهائية")
            journal = read_journal(path)
            self.assertEqual(len(journal["reviews"]), 2)
            self.assertEqual(latest_reviews(journal)["red-ar"]["state"], "approved")
            self.assertFalse((Path(root) / "published").exists())

    def test_invalid_state_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "reviews.json"
            with self.assertRaises(ValueError):
                append_review(path, episode_id="red-ar", state="published")
            self.assertFalse(path.exists())

    def test_reject_invalid_ids_and_long_notes(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "reviews.json"
            for eid in ("../red", "", "a b"):
                with self.subTest(eid=eid):
                    with self.assertRaises(ValueError):
                        append_review(path, episode_id=eid, state="approved")
            with self.assertRaises(ValueError):
                append_review(path, episode_id="red", state="approved", note="x" * 2001)


if __name__ == "__main__":
    unittest.main()
