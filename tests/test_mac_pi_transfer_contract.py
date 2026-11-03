import tempfile
import subprocess
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
                if args[0] == "ssh":
                    calls.append(("publish", args[-1], b""))
                else:
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
            self.assertEqual([x[0] for x in calls], [".mp4", ".json", "publish"])
            self.assertEqual(calls[0][1], result["manifest"]["filename"])
            self.assertEqual(calls[1][1], calls[0][1][:-4] + ".json")
            self.assertIn("." + calls[1][1] + ".incoming", calls[2][1])
            self.assertIn(calls[1][1], calls[2][1])

    def test_failed_media_rsync_never_publishes_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "render.mp4"
            video.write_bytes(b"test render")
            calls = []
            def fail_first(args, **kwargs):
                calls.append(Path(args[-2]).suffix if args[0] != "ssh" else "publish")
                raise subprocess.CalledProcessError(23, args)
            with patch("kidsstudio.mac_pi_media_transfer.subprocess.run", side_effect=fail_first):
                with self.assertRaises(subprocess.CalledProcessError):
                    transfer_to_pi(video, episode_id="colors-red",
                                   ssh_target="kidsstudio@pi.local",
                                   remote_staging_dir="/var/lib/kidsstudio/staging",
                                   dry_run=False)
            self.assertEqual(calls, [".mp4"])

    def test_failed_manifest_rsync_does_not_report_transfer_success(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "render.mp4"
            video.write_bytes(b"test render")
            calls = []
            def fail_manifest(args, **kwargs):
                calls.append(Path(args[-2]).suffix)
                if len(calls) == 2:
                    raise subprocess.CalledProcessError(23, args)
            with patch("kidsstudio.mac_pi_media_transfer.subprocess.run", side_effect=fail_manifest):
                with self.assertRaises(subprocess.CalledProcessError):
                    transfer_to_pi(video, episode_id="colors-red",
                                   ssh_target="kidsstudio@pi.local",
                                   remote_staging_dir="/var/lib/kidsstudio/staging",
                                   dry_run=False)
            self.assertEqual(calls, [".mp4", ".json"])

    def test_failed_publish_keeps_manifest_hidden(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "render.mp4"
            video.write_bytes(b"test render")
            calls = []
            def fail_publish(args, **kwargs):
                calls.append(args[0])
                if args[0] == "ssh":
                    raise subprocess.CalledProcessError(1, args)
            with patch("kidsstudio.mac_pi_media_transfer.subprocess.run", side_effect=fail_publish):
                with self.assertRaises(subprocess.CalledProcessError):
                    transfer_to_pi(video, episode_id="colors-red",
                                   ssh_target="kidsstudio@pi.local",
                                   remote_staging_dir="/var/lib/kidsstudio/staging",
                                   dry_run=False)
            self.assertEqual(calls, ["rsync", "rsync", "ssh"])

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
