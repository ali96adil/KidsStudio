"""Tests for offline Mac/Pi master inventory."""
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_master_handoff import inventory, verify_inventory, HandoffError


class MasterHandoffTests(unittest.TestCase):
    def test_inventory_and_detect_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "render").mkdir()
            master = root / "render" / "preview.mp4"
            master.write_bytes(b"mp4 test fixture")
            report = inventory(root, master=master, episode_id="colors-ar-001")
            self.assertEqual(report["status"], "MASTER_INVENTORIED_NOT_TRANSFERRED")
            self.assertFalse(report["youtube_upload_authorized"])
            self.assertEqual(verify_inventory(root, report)["status"], "MASTER_HASH_VERIFIED")
            master.write_bytes(b"changed")
            with self.assertRaises(HandoffError):
                verify_inventory(root, report)

    def test_master_must_be_inside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "episode"
            root.mkdir()
            external = Path(tmp) / "other.mp4"
            external.write_bytes(b"file")
            with self.assertRaises(HandoffError):
                inventory(root, master=external, episode_id="colors-ar-001")


if __name__ == "__main__":
    unittest.main()
