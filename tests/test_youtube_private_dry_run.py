import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.youtube_private_dry_run import build_private_upload_dry_run


class YouTubePrivateDryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.data = b"synthetic video bytes"
        (self.root / "episode.mp4").write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()

    def preview(self, **changes):
        args = dict(private_root=str(self.root), relative_path="episode.mp4",
                    expected_sha256=self.sha, episode_id="colors_ar_01",
                    title="تعلم الألوان", language="ar")
        args.update(changes)
        return build_private_upload_dry_run(**args)

    def test_private_only_preview_with_explicit_authorization(self):
        result = self.preview(owner_private_upload_authorized=True)
        self.assertEqual(result["status"], "DRY_RUN_READY")
        self.assertEqual(result["youtube_request_preview"]["status"]["privacyStatus"],
                         "private")
        self.assertFalse(result["network_called"])
        self.assertFalse(result["credentials_loaded"])
        self.assertFalse(result["upload_submitted"])
        self.assertFalse(result["publication_approved"])

    def test_default_blocked(self):
        self.assertEqual(self.preview()["status"], "BLOCKED")

    def test_bad_hash_blocks_even_with_permission(self):
        self.assertEqual(self.preview(owner_private_upload_authorized=True,
                                      expected_sha256="0" * 64)["status"], "BLOCKED")

    def test_english_metadata(self):
        result = self.preview(owner_private_upload_authorized=True,
                              title="Learn Colors", language="en")
        self.assertEqual(result["youtube_request_preview"]["snippet"]["defaultLanguage"],
                         "en")

    def test_invalid_title(self):
        with self.assertRaises(ValueError):
            self.preview(title=" " * 101)

    def test_invalid_language(self):
        with self.assertRaises(ValueError):
            self.preview(language="fr")


if __name__ == "__main__":
    unittest.main()
