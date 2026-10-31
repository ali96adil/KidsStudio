"""M67 regression: SSH remote paths must be canonical."""
import unittest
from unittest.mock import Mock
from pathlib import Path
import tempfile

from kidsstudio.m67_master_handoff import inventory
from kidsstudio.m67_pi_ssh_transfer import transfer, TransferError


class SSHGuardTests(unittest.TestCase):
    def test_dotdot_remote_path_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            master = root / "master.mp4"
            master.write_bytes(b"fixture")
            manifest = inventory(root, master=master, episode_id="colors-ar-001")
            with self.assertRaises(TransferError):
                transfer(root, manifest, host="pi.local", user="studio",
                         remote_dir="/home/studio/../incoming", runner=Mock())
