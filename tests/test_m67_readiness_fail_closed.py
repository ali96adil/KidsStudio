"""Readiness status must fail closed for fabricated status strings."""
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m67_readiness_summary import readiness


class ReadinessFailClosedTests(unittest.TestCase):
    def test_arbitrary_status_cannot_complete_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "jobs.json").write_text(json.dumps({"status": "EVERYTHING_IS_DONE"}))
            report = readiness(root)
            self.assertIn("jobs", report["incomplete_stages"])
            self.assertEqual(report["status"], "M67_EVIDENCE_INCOMPLETE")
