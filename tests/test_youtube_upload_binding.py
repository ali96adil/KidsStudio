import tempfile
import unittest
from pathlib import Path

from kidsstudio.youtube_upload_binding import UploadBindingStore


class UploadBindingTests(unittest.TestCase):
    def test_exact_latest_binding(self):
        with tempfile.TemporaryDirectory() as root:
            store = UploadBindingStore(Path(root) / "bindings.db")
            store.initialize()
            first_hash = "a" * 64
            second_hash = "b" * 64
            first_id = "Abc123_defG"
            second_id = "Def456_ghiJ"
            self.assertFalse(store.matches_latest("red", first_hash, first_id, "channel"))
            store.record("red", first_hash, first_id, "channel")
            self.assertTrue(store.matches_latest("red", first_hash, first_id, "channel"))
            self.assertFalse(store.matches_latest("red", first_hash, first_id, "other"))
            store.record("red", second_hash, second_id, "channel")
            self.assertFalse(store.matches_latest("red", first_hash, first_id, "channel"))
            self.assertTrue(store.matches_latest("red", second_hash, second_id, "channel"))

    def test_video_id_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as root:
            store = UploadBindingStore(Path(root) / "bindings.db")
            store.initialize()
            store.record("red", "a" * 64, "Abc123_defG", "channel")
            with self.assertRaises(Exception):
                store.record("blue", "b" * 64, "Abc123_defG", "channel")

    def test_invalid_video_id(self):
        with tempfile.TemporaryDirectory() as root:
            store = UploadBindingStore(Path(root) / "bindings.db")
            store.initialize()
            with self.assertRaises(ValueError):
                store.record("red", "a" * 64, "bad", "channel")


if __name__ == "__main__":
    unittest.main()
