import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.inbox_promote import promote_verified_file


class InboxPromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "incoming"
        self.target = self.root / "private"
        self.source.mkdir(mode=0o700)
        self.target.mkdir(mode=0o700)
        self.data = b"synthetic episode bytes" * 1024
        (self.source / "episode.mp4").write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def promote(self, **overrides):
        args = dict(source_root=self.source, relative_path="episode.mp4",
                    destination_root=self.target, destination_name="episode.mp4",
                    expected_sha256=self.sha)
        args.update(overrides)
        return promote_verified_file(**args)

    def test_success_is_private_and_unapproved(self):
        result = self.promote()
        self.assertEqual(result["status"], "PROMOTED_PRIVATE")
        self.assertFalse(result["upload_approved"])
        self.assertFalse(result["network_transfer_performed"])
        self.assertEqual((self.target / "episode.mp4").read_bytes(), self.data)

    def test_existing_destination_never_overwritten(self):
        dest = self.target / "episode.mp4"
        dest.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            self.promote()
        self.assertEqual(dest.read_bytes(), b"existing")

    def test_corrupted_source_rejected_without_output(self):
        (self.source / "episode.mp4").write_bytes(b"bad")
        with self.assertRaises(ValueError):
            self.promote()
        self.assertFalse((self.target / "episode.mp4").exists())

    def test_traversal_name_rejected(self):
        with self.assertRaises(ValueError):
            self.promote(destination_name="../outside.mp4")

    def test_git_destination_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaises(ValueError):
            self.promote()

    def test_non_private_destination_rejected(self):
        self.target.chmod(0o755)
        with self.assertRaises(ValueError):
            self.promote()

    def test_second_promotion_rejected_without_temp_files(self):
        self.promote()
        with self.assertRaises(FileExistsError):
            self.promote()
        self.assertEqual(sorted(p.name for p in self.target.iterdir()),
                         ["episode.mp4"])
        self.assertEqual((self.target / "episode.mp4").read_bytes(), self.data)

    def test_symlink_destination_rejected_without_touching_target(self):
        outside = self.root / "untouched.txt"
        outside.write_bytes(b"untouched")
        (self.target / "episode.mp4").symlink_to(outside)
        with self.assertRaises(FileExistsError):
            self.promote()
        self.assertEqual(outside.read_bytes(), b"untouched")

    def test_same_root_rejected(self):
        with self.assertRaises(ValueError):
            self.promote(destination_root=self.source)

    def test_source_traversal_rejected(self):
        with self.assertRaises(ValueError):
            self.promote(relative_path="../episode.mp4")


if __name__ == "__main__":
    unittest.main()
