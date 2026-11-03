"""Offline rsync/SSH retry simulation: manifest remains hidden until publish."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.mac_pi_media_transfer import transfer_to_pi


class TransferRetryTests(unittest.TestCase):
    def test_interrupted_publish_then_retry(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            staging = base / "staging"
            staging.mkdir()
            video = base / "render.mp4"
            video.write_bytes(b"episode render")
            commands = []
            fail_once = [True]

            def simulate(argv, **kwargs):
                commands.append(argv[0])
                if argv[0] == "rsync":
                    source = Path(argv[-2])
                    remote = argv[-1].split(":", 1)[1]
                    filename = source.name if remote.endswith("/") else Path(remote).name
                    shutil.copy2(source, staging / filename)
                    return
                if argv[0] == "ssh":
                    if fail_once[0]:
                        fail_once[0] = False
                        raise subprocess.CalledProcessError(255, argv)
                    parts = argv[-1].split(" ")
                    (staging / Path(parts[2]).name).rename(staging / Path(parts[3]).name)
                    return
                raise AssertionError("unexpected command")

            with patch("kidsstudio.mac_pi_media_transfer.subprocess.run", side_effect=simulate):
                with self.assertRaises(subprocess.CalledProcessError):
                    transfer_to_pi(video, episode_id="colors_001", ssh_target="pi@host",
                                   remote_staging_dir="/home/pi/staging", dry_run=False)
                self.assertEqual(list(staging.glob("*.json")), [])
                self.assertEqual(len(list(staging.glob("*.incoming"))), 1)
                result = transfer_to_pi(video, episode_id="colors_001", ssh_target="pi@host",
                                        remote_staging_dir="/home/pi/staging", dry_run=False)

            self.assertTrue(result["transferred"])
            self.assertEqual(len(list(staging.glob("*.mp4"))), 1)
            self.assertEqual(len(list(staging.glob("*.json"))), 1)
            self.assertEqual(list(staging.glob("*.incoming")), [])
            self.assertEqual(commands, ["rsync", "rsync", "ssh", "rsync", "rsync", "ssh"])


if __name__ == "__main__":
    unittest.main()
