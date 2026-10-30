"""M67 handoff integrity and fail-closed production tests."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_production_handoff import (
    build_manifest, audit_assets, audit_master, ProductionHandoffError,
)

ROOT = Path(__file__).resolve().parents[1]


class M67ProductionHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(
            (ROOT / "examples/m67_colors_red_episode_001.json").read_text(
                encoding="utf-8"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = build_manifest(self.storyboard)

    def test_initial_state_blocks_render_and_transfer(self):
        self.assertEqual(audit_assets(self.manifest, self.root)["status"],
                         "ASSETS_BLOCKED")
        self.assertFalse(audit_master(self.manifest, self.root)["pi_transfer_authorized"])

    def populate(self):
        for item in self.manifest["assets"]:
            for kind in ("art", "voice"):
                path = self.root / item[kind]
                path.parent.mkdir(exist_ok=True)
                payload = (kind + str(item["beat"])).encode()
                path.write_bytes(payload)
                item[kind + "_sha256"] = hashlib.sha256(payload).hexdigest()
            item["visual_qa"] = "PASS"
            item["voice_qa"] = "PASS"

    def test_all_verified_assets_admit_render_not_upload(self):
        self.populate()
        result = audit_assets(self.manifest, self.root)
        self.assertTrue(result["render_authorized"])
        self.assertFalse(result["youtube_upload_authorized"])

    def test_tampering_blocks_render(self):
        self.populate()
        (self.root / "art/beat_01.png").write_bytes(b"changed")
        self.assertFalse(audit_assets(self.manifest, self.root)["render_authorized"])

    def test_symlink_asset_rejected(self):
        self.populate()
        path = self.root / "art/beat_01.png"
        path.unlink()
        path.symlink_to(self.root / "voice/beat_01.wav")
        self.assertFalse(audit_assets(self.manifest, self.root)["render_authorized"])

    def test_master_gate_requires_render_qa(self):
        self.populate()
        file = self.root / self.manifest["render"]["file"]
        file.parent.mkdir()
        file.write_bytes(b"synthetic-test-only")
        self.manifest["render"]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
        self.assertFalse(audit_master(self.manifest, self.root)["pi_transfer_authorized"])
        self.manifest["render"]["qa"] = "PASS"
        result = audit_master(self.manifest, self.root)
        self.assertTrue(result["pi_transfer_authorized"])
        self.assertFalse(result["public_release_authorized"])

    def test_public_release_fails_closed(self):
        self.manifest["public_release_authorized"] = True
        with self.assertRaises(ProductionHandoffError):
            audit_assets(self.manifest, self.root)


if __name__ == "__main__":
    unittest.main()
