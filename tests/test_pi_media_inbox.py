import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_media_inbox import build_manifest, ingest_media
from kidsstudio.mac_pi_media_transfer import transfer_to_pi


class MediaInboxTests(unittest.TestCase):
    def test_verified_ingest_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            video = folder / "red.mp4"
            video.write_bytes(b"example media")
            manifest = build_manifest(video, "red-ar")
            inbox = folder / "inbox"
            target = ingest_media(video, manifest, inbox)
            self.assertEqual(target.read_bytes(), video.read_bytes())
            self.assertEqual(ingest_media(video, manifest, inbox), target)

    def test_rejects_corrupted_transfer(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            video = folder / "red.mp4"
            video.write_bytes(b"original")
            manifest = build_manifest(video, "red-ar")
            video.write_bytes(b"corrupted")
            with self.assertRaises(ValueError):
                ingest_media(video, manifest, folder / "inbox")
            self.assertEqual(list((folder / "inbox").glob("*.mp4")), [])

    def test_dry_run_does_not_transfer(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "red.mp4"
            video.write_bytes(b"example media")
            result = transfer_to_pi(
                video, episode_id="red-ar", ssh_target="kidsstudio@pi.local",
                remote_staging_dir="/var/lib/kidsstudio/staging",
            )
            self.assertFalse(result["transferred"])
            self.assertEqual(result["manifest"]["episode_id"], "red-ar")


if __name__ == "__main__":
    unittest.main()
