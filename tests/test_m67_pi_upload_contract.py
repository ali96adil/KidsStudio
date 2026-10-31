"""M67 Pi upload contract tests."""
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_master_handoff import inventory
from kidsstudio.m67_pi_upload_contract import assess, REQUIRED


class PiUploadContractTests(unittest.TestCase):
    def test_raw_drop_not_eligible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            master = root / "episode.mp4"
            master.write_bytes(b"fixture")
            manifest = inventory(root, master=master, episode_id="colors-ar-001")
            result = assess(root, manifest)
            self.assertEqual(result["status"], "M67_RAW_MASTER_NOT_REGISTERED_WITH_PI_INBOX")
            self.assertFalse(result["pi_upload_authorized"])

    def test_self_declared_approval_is_not_pi_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            master = root / "episode.mp4"
            master.write_bytes(b"fixture")
            manifest = inventory(root, master=master, episode_id="colors-ar-001")
            claimed = {name: "claimed" for name in REQUIRED}
            result = assess(root, manifest, claimed)
            self.assertEqual(result["status"], "M67_PI_SIDE_VERIFICATION_REQUIRED")
            self.assertFalse(result["pi_upload_authorized"])


if __name__ == "__main__":
    unittest.main()
