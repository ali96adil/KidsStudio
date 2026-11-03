import tempfile
import unittest
from pathlib import Path

from kidsstudio.mac_pi_transfer_precheck import precheck


class MacPiTransferPrecheckTests(unittest.TestCase):
    def test_valid_video_is_ready_without_transfer(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "render.mp4"
            video.write_bytes(b"offline test video bytes")
            result = precheck(video, "colors_001", "pi@raspberrypi.local", "/home/pi/staging")
            self.assertEqual(result["status"], "READY_FOR_TRANSFER_NOT_TRANSFERRED")
            self.assertTrue(result["remote_video_filename"].startswith("colors_001-"))
            self.assertTrue(result["remote_video_filename"].endswith(".mp4"))
            self.assertEqual(result["remote_manifest_filename"],
                             result["remote_video_filename"][:-4] + ".json")
            self.assertEqual(result["size"], video.stat().st_size)
            self.assertFalse(result["network_checked"])
            self.assertFalse(result["youtube_uploaded"])
            self.assertFalse(result["public_release_authorized"])

    def test_bad_target_and_empty_video_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "render.mp4"
            video.write_bytes(b"video")
            with self.assertRaises(ValueError):
                precheck(video, "colors_001", "pi@host;rm", "/home/pi/staging")
            with self.assertRaises(ValueError):
                precheck(video, "colors_001", "pi@host", "/home/pi/../staging")
            video.write_bytes(b"")
            with self.assertRaises(ValueError):
                precheck(video, "colors_001", "pi@host", "/home/pi/staging")

    def test_symlink_video_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "render.mp4"
            video.write_bytes(b"video")
            link = Path(tmp) / "link.mp4"
            link.symlink_to(video)
            with self.assertRaises(ValueError):
                precheck(link, "colors_001", "pi@host", "/home/pi/staging")


if __name__ == "__main__":
    unittest.main()
