import tempfile
from unittest.mock import patch
import unittest
from pathlib import Path

from kidsstudio.mac_pi_offline_end_to_end import run_offline_trial


class MacPiOfflineEndToEndTests(unittest.TestCase):
    def test_simulated_transfer_and_sha_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "colors.mp4"
            video.write_bytes(b"original local video sample")
            result = run_offline_trial(video, "colors_001")
            self.assertEqual(result["status"], "OFFLINE_MAC_PI_TRIAL_PASSED")
            self.assertEqual(result["size"], video.stat().st_size)
            self.assertTrue(result["simulated_pi_only"])
            self.assertFalse(result["real_pi_tested"])
            self.assertFalse(result["youtube_uploaded"])
            self.assertFalse(result["public_release_authorized"])

    def test_changed_source_during_copy_rejected(self):
        import shutil
        original_copy = shutil.copyfile
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "colors.mp4"
            video.write_bytes(b"original bytes")
            def tamper_copy(src, dst):
                result = original_copy(src, dst)
                Path(dst).write_bytes(b"corrupted copy")
                return result
            with patch("kidsstudio.mac_pi_offline_end_to_end.shutil.copyfile", side_effect=tamper_copy):
                with self.assertRaises(ValueError):
                    run_offline_trial(video, "colors_001")

    def test_empty_video_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "empty.mp4"
            video.touch()
            with self.assertRaises(ValueError):
                run_offline_trial(video, "colors_001")

    def test_invalid_episode_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "colors.mp4"
            video.write_bytes(b"data")
            with self.assertRaises(ValueError):
                run_offline_trial(video, "../unsafe")


if __name__ == "__main__":
    unittest.main()
