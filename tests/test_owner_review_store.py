import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_review_store import OwnerReviewStore


class OwnerReviewStoreTests(unittest.TestCase):
    def test_latest_and_immutable_history(self):
        with tempfile.TemporaryDirectory() as root:
            store = OwnerReviewStore(Path(root) / "reviews.sqlite")
            store.initialize()
            store.record(episode_id="colors-red", state="changes_requested", note="Audio")
            store.record(episode_id="colors-red", state="approved", note="OK")
            self.assertEqual(store.latest()["colors-red"]["state"], "approved")
            history = store.history("colors-red")
            self.assertEqual([x["state"] for x in history], ["approved", "changes_requested"])

    def test_reject_publish_and_bad_ids(self):
        with tempfile.TemporaryDirectory() as root:
            store = OwnerReviewStore(Path(root) / "reviews.sqlite")
            store.initialize()
            with self.assertRaises(ValueError):
                store.record(episode_id="red", state="published")
            with self.assertRaises(ValueError):
                store.record(episode_id="../red", state="approved")
            self.assertEqual(store.latest(), {})

    def test_multiple_instances_preserve_history(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "reviews.sqlite"
            first, second = OwnerReviewStore(path), OwnerReviewStore(path)
            first.initialize()
            first.record(episode_id="red", state="needs_review")
            second.record(episode_id="red", state="changes_requested")
            self.assertEqual(len(first.history("red")), 2)


if __name__ == "__main__":
    unittest.main()
