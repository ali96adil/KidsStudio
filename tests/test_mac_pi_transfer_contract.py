import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.mac_pi_media_transfer import transfer_to_pi


class TransferContractTests(unittest.TestCase):
    def test_manifest_follows_media_with_matching_names(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "render.mp4"
            video.write_bytes(b"test render")
            calls = []
            def record(args, **kwargs):
                source = Path(args[-2])
                calls.append((source.suffix, source.name, source.read_bytes()))
            with patch("kidsstudio.mac_pi_media_transfer.subprocess.run", side_effect=record):
                result = transfer_to_pi(
                    video, episode_id="colors-red",
                    ssh_target="kidsstudio@pi.local",
                    remote_staging_dir="/var/lib/kidsstudio/private-upload/staging",
                    dry_run=False,
                )
            self.assertTrue(result["transferred"])
            self.assertEqual([x[0] for x in calls], [".mp4", ".json"])
            self.assertEqual(calls[0][1], result["manifest"]["filename"])
            self.assertEqual(calls[1][1], calls[0][1][:-4] + ".json")

    def test_rejects_unsafe_remote_path(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "render.mp4"
            video.write_bytes(b"test")
            with self.assertRaises(ValueError):
                transfer_to_pi(video, episode_id="colors-red",
                               ssh_target="kidsstudio@pi.local",
                               remote_staging_dir="/tmp/../unsafe")


if __name__ == "__main__":
    unittest.main()
