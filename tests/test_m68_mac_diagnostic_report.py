"""Mac diagnostic report tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.m68_mac_diagnostic_report import collect, main


class MacDiagnosticTests(unittest.TestCase):
    def test_inventory_only_does_not_run_models(self):
        result = collect(
            endpoint="http://127.0.0.1:11434/api/chat",
            dependency_probe=lambda **kwargs: {"missing": [], "tools": {}})
        self.assertEqual(result["status"], "INVENTORY_ONLY")
        self.assertFalse(result["model_inference_executed"])
        self.assertFalse(result["public_release_authorized"])

    def test_report_is_private_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "mac-report.json"
            with patch("kidsstudio.m68_mac_diagnostic_report.collect",
                       return_value={"status": "INVENTORY_ONLY",
                                     "ready_for_manual_inference_trial": False,
                                     "public_release_authorized": False}):
                self.assertEqual(main(["--output", str(target)]), 0)
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                self.assertEqual(main(["--output", str(target)]), 2)
                self.assertEqual(json.loads(target.read_text())["status"],
                                 "INVENTORY_ONLY")
