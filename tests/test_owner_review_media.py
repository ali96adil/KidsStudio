import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_review_media import load_registry, video_mime


class ReviewMediaTests(unittest.TestCase):
    def test_local_video_attachment(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            media = root / "media"
            media.mkdir()
            (media / "red.mp4").write_bytes(b"example")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"schema_version": 1, "episodes": {"red": "red.mp4"}}))
            result = load_registry(registry, media)
            self.assertEqual(result["red"], (media / "red.mp4").resolve())
            self.assertEqual(video_mime(result["red"]), "video/mp4")

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            media = root / "media"
            media.mkdir()
            (root / "secret.mp4").write_bytes(b"secret")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"schema_version": 1, "episodes": {"red": "../secret.mp4"}}))
            with self.assertRaises(ValueError):
                load_registry(registry, media)

    def test_outside_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            media = root / "media"
            media.mkdir()
            (root / "secret.mp4").write_bytes(b"secret")
            (media / "linked.mp4").symlink_to(root / "secret.mp4")
            registry = root / "registry.json"
            registry.write_text(json.dumps({"schema_version": 1, "episodes": {"red": "linked.mp4"}}))
            with self.assertRaises(ValueError):
                load_registry(registry, media)


if __name__ == "__main__":
    unittest.main()
