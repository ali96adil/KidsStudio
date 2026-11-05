import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.private_handoff import prepare_private_handoff


class PrivateHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "ready"
        self.root.mkdir(mode=0o700)
        self.data = b"synthetic"
        (self.root / "episode.mp4").write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def prepare(self, **changes):
        args = dict(private_root=self.root, relative_path="episode.mp4",
                    expected_sha256=self.sha, episode_id="colors_ar_01")
        args.update(changes)
        return prepare_private_handoff(**args)

    def test_default_blocks(self):
        self.assertEqual(self.prepare()["status"], "BLOCKED")

    def test_explicit_private_permission_not_upload(self):
        report = self.prepare(owner_private_upload_authorized=True)
        self.assertEqual(report["status"], "READY_FOR_SEPARATE_PRIVATE_UPLOAD")
        self.assertEqual(report["visibility"], "private")
        self.assertFalse(report["upload_submitted"])
        self.assertFalse(report["publication_approved"])
        self.assertTrue(report["requires_owner_video_review"])
        self.assertNotIn(str(self.root), str(report))

    def test_tamper_never_eligible(self):
        self.assertEqual(self.prepare(expected_sha256="0"*64,
                                      owner_private_upload_authorized=True)["status"],
                         "BLOCKED")

    def test_invalid_episode_id_rejected(self):
        with self.assertRaises(ValueError):
            self.prepare(episode_id="../secret")

    def test_does_not_mutate_file(self):
        self.prepare(owner_private_upload_authorized=True)
        self.assertEqual((self.root / "episode.mp4").read_bytes(), self.data)


if __name__ == "__main__":
    unittest.main()
