import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.mac_pi_verified_transfer import transfer_and_verify


class VerifiedTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.video = Path(self.tmp.name) / "render.mp4"
        self.video.write_bytes(b"render data")
        self.kwargs = dict(video_path=self.video, episode_id="colors_001",
                           ssh_target="pi@host", remote_staging_dir="/home/pi/staging")

    def test_dry_run_never_contacts_ssh(self):
        with patch("kidsstudio.mac_pi_media_transfer.subprocess.run") as runner:
            result = transfer_and_verify(**self.kwargs)
            runner.assert_not_called()
        self.assertEqual(result["status"], "MAC_PI_TRANSFER_DRY_RUN")
        self.assertFalse(result["transferred"])
        self.assertFalse(result["pi_verified"])

    def test_successful_transfer_and_verify(self):
        manifest = dict(episode_id="colors_001", size=11, sha256="a" * 64)
        with patch("kidsstudio.mac_pi_verified_transfer.transfer_to_pi",
                   return_value=dict(manifest=manifest, transferred=True)) as transfer, patch(
                   "kidsstudio.mac_pi_verified_transfer.verify_remote",
                   return_value=dict(episode_id="colors_001", size=11, sha256="a" * 64,
                                     youtube_uploaded=False, public_release_authorized=False)) as verify:
            result = transfer_and_verify(**self.kwargs, execute=True)
        self.assertEqual(result["status"], "MAC_PI_TRANSFER_AND_REMOTE_VERIFY_PASSED")
        self.assertTrue(result["pi_verified"])
        self.assertFalse(result["youtube_uploaded"])
        self.assertFalse(result["public_release_authorized"])
        self.assertFalse(transfer.call_args.kwargs["dry_run"])
        verify.assert_called_once()

    def test_digest_mismatch_rejected(self):
        manifest = dict(episode_id="colors_001", size=11, sha256="a" * 64)
        with patch("kidsstudio.mac_pi_verified_transfer.transfer_to_pi",
                   return_value=dict(manifest=manifest, transferred=True)), patch(
                   "kidsstudio.mac_pi_verified_transfer.verify_remote",
                   return_value=dict(size=11, sha256="b" * 64)):
            with self.assertRaises(ValueError):
                transfer_and_verify(**self.kwargs, execute=True)

    def test_failed_transfer_does_not_verify(self):
        with patch("kidsstudio.mac_pi_verified_transfer.transfer_to_pi",
                   side_effect=RuntimeError("rsync failed")), patch(
                   "kidsstudio.mac_pi_verified_transfer.verify_remote") as verify:
            with self.assertRaises(RuntimeError):
                transfer_and_verify(**self.kwargs, execute=True)
            verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
