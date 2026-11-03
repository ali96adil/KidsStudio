import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.mac_pi_remote_verify import verify_remote
from kidsstudio.pi_media_inbox import build_manifest


class RemoteVerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.video = Path(self.tmp.name) / "render.mp4"
        self.video.write_bytes(b"test educational episode")
        self.manifest = build_manifest(self.video, "colors_001")

    def invoke(self, stdout):
        with patch("kidsstudio.mac_pi_remote_verify.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, stdout, "")) as runner:
            result = verify_remote(self.video, episode_id="colors_001",
                                   ssh_target="pi@host",
                                   remote_staging_dir="/home/pi/staging")
            self.assertEqual(runner.call_count, 1)
            args = runner.call_args.args[0]
            self.assertEqual(args[:4], ["ssh", "-o", "BatchMode=yes", "--"])
            self.assertIn("--manifest colors_001-", args[-1])
            return result

    def test_success(self):
        report = dict(status="PI_MEDIA_VERIFIED_NOT_QUEUED",
                      episode_id="colors_001", size=self.manifest["size"],
                      sha256=self.manifest["sha256"], youtube_uploaded=False,
                      public_release_authorized=False)
        result = self.invoke(json.dumps(report))
        self.assertTrue(result["pi_verified"])
        self.assertFalse(result["youtube_uploaded"])

    def test_mismatch_fails_closed(self):
        report = dict(status="PI_MEDIA_VERIFIED_NOT_QUEUED",
                      episode_id="colors_001", size=self.manifest["size"],
                      sha256="0" * 64, youtube_uploaded=False,
                      public_release_authorized=False)
        with patch("kidsstudio.mac_pi_remote_verify.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, json.dumps(report), "")):
            with self.assertRaises(ValueError):
                verify_remote(self.video, episode_id="colors_001",
                              ssh_target="pi@host", remote_staging_dir="/home/pi/staging")

    def test_malformed_response_fails_closed(self):
        with patch("kidsstudio.mac_pi_remote_verify.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, "not-json", "")):
            with self.assertRaises(ValueError):
                verify_remote(self.video, episode_id="colors_001",
                              ssh_target="pi@host", remote_staging_dir="/home/pi/staging")

    def test_rejects_unsafe_ssh_target_without_network(self):
        with patch("kidsstudio.mac_pi_remote_verify.subprocess.run") as runner:
            with self.assertRaises(ValueError):
                verify_remote(self.video, episode_id="colors_001",
                              ssh_target="pi@host;bad", remote_staging_dir="/home/pi/staging")
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
