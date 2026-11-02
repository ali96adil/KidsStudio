import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_media_approval import MediaApprovalStore, sha256_video


class MediaApprovalTests(unittest.TestCase):
    def test_approval_is_exact_video_specific(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            video = folder / "episode.mp4"
            video.write_bytes(b"first render")
            first = sha256_video(video)
            store = MediaApprovalStore(folder / "approvals.db")
            store.initialize()
            self.assertFalse(store.approved_for("red-ar", first))
            store.record("red-ar", first, "approved")
            self.assertTrue(store.approved_for("red-ar", first))
            video.write_bytes(b"second render")
            second = sha256_video(video)
            self.assertNotEqual(first, second)
            self.assertFalse(store.approved_for("red-ar", second))
            store.record("red-ar", second, "approved")
            self.assertTrue(store.approved_for("red-ar", second))
            store.record("red-ar", second, "changes_requested")
            self.assertFalse(store.approved_for("red-ar", second))

    def test_reject_invalid_hash(self):
        with tempfile.TemporaryDirectory() as root:
            store = MediaApprovalStore(Path(root) / "approvals.db")
            store.initialize()
            with self.assertRaises(ValueError):
                store.record("red-ar", "bad", "approved")
            self.assertFalse(store.approved_for("red-ar", "bad"))


if __name__ == "__main__":
    unittest.main()
