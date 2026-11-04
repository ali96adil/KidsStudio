"""Tests for verified SSH delivery of M67 master to Pi."""
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_master_handoff import inventory
from kidsstudio.m67_pi_ssh_transfer import transfer, TransferError


class Completed:
    def __init__(self, stdout=""):
        self.stdout = stdout


class PiTransferTests(unittest.TestCase):
    def test_verified_transfer_and_no_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = root / "master.mp4"
            movie.write_bytes(b"sample")
            manifest = inventory(root, master=movie, episode_id="colors-ar-001")
            digest = manifest["master"]["sha256"]
            commands = []
            def fake_run(cmd, **kwargs):
                commands.append(cmd)
                if "sha256sum" in cmd:
                    return Completed(digest + "  file.mp4\n")
                return Completed()
            result = transfer(root, manifest, host="raspberrypi.local",
                              user="studio", remote_dir="/home/studio/incoming",
                              runner=fake_run)
            self.assertEqual(result["status"], "TRANSFERRED_TO_PI_HASH_VERIFIED")
            self.assertFalse(result["youtube_upload_authorized"])
            self.assertEqual(sum("sha256sum" in cmd for cmd in commands), 2)
            self.assertEqual(sum(cmd[0] == "scp" for cmd in commands), 1)

    def test_reject_host_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            movie = root / "master.mp4"
            movie.write_bytes(b"sample")
            manifest = inventory(root, master=movie, episode_id="colors-ar-001")
            with self.assertRaises(TransferError):
                transfer(root, manifest, host="pi;echo unsafe",
                         user="studio", remote_dir="/tmp")


if __name__ == "__main__":
    unittest.main()
