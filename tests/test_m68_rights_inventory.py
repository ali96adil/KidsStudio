"""Rights inventory documents provenance but never grants legal clearance."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m68_rights_inventory import audit


class RightsInventoryTests(unittest.TestCase):
    def test_hash_bound_asset_is_documented_not_legally_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "character.png"
            asset.write_bytes(b"original-pixels")
            manifest = root / "rights.json"
            payload = {"schema_version": 1, "video_sha256": "a" * 64,
                       "assets": [{"id": "bunny", "kind": "image",
                                   "rights_basis": "original",
                                   "source": "Created for Kids Studio",
                                   "evidence_reference": "project asset ledger 001",
                                   "path": str(asset),
                                   "sha256": hashlib.sha256(asset.read_bytes()).hexdigest()}]}
            manifest.write_text(json.dumps(payload))
            result = audit(manifest, expected_video_sha256="a" * 64)
            self.assertEqual(result["status"],
                             "RIGHTS_INVENTORY_DOCUMENTED_NOT_LEGALLY_VERIFIED")
            self.assertFalse(result["legal_rights_independently_verified"])
            self.assertFalse(result["youtube_upload_authorized"])
            asset.write_bytes(b"modified")
            result = audit(manifest, expected_video_sha256="a" * 64)
            self.assertIn("bunny:asset_hash_mismatch", result["reasons"])

    def test_missing_asset_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "rights.json"
            manifest.write_text(json.dumps({
                "schema_version": 1, "video_sha256": "b" * 64,
                "assets": [{"id": "sound", "kind": "audio",
                            "rights_basis": "licensed",
                            "source": "Sound provider license",
                            "evidence_reference": "receipt 12345",
                            "path": str(root / "missing.wav"),
                            "sha256": "a" * 64}]}))
            result = audit(manifest, expected_video_sha256="b" * 64)
            self.assertEqual(result["status"], "BLOCKED_RIGHTS_INVENTORY")
            self.assertIn("sound:asset_file_missing", result["reasons"])
