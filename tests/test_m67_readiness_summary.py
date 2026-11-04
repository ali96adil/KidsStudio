"""Tests for M67 production readiness inventory."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_readiness_summary import readiness


class ReadinessTests(unittest.TestCase):
    def test_missing_evidence_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            report = readiness(temp)
            self.assertEqual(report["status"], "M67_EVIDENCE_INCOMPLETE")
            self.assertIn("master", report["incomplete_stages"])
            self.assertFalse(report["public_release_authorized"])

    def test_recorded_status_is_not_hardware_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "master_inventory.json").write_text(json.dumps(
                {"status": "MASTER_INVENTORIED_NOT_TRANSFERRED"}))
            report = readiness(root)
            self.assertEqual(report["observed"]["master"],
                             "MASTER_INVENTORIED_NOT_TRANSFERRED")
            self.assertFalse(report["pi_private_upload_confirmed"])
