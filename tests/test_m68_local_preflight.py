"""M68 one-command preflight tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.m68_local_preflight import main, preflight


class PreflightTests(unittest.TestCase):
    def test_missing_handoff_is_explicit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            code = main(["--root", directory, "--handoff",
                         str(Path(directory) / "missing.json")])
            self.assertEqual(code, 2)

    @patch("kidsstudio.m68_local_preflight.audit")
    def test_report_never_claims_physical_qualification(self, mock_audit):
        mock_audit.return_value = {
            "status": "M68_CONSOLIDATED_REVIEW_BLOCKED",
            "blockers": ["audio_independent_review_missing"],
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            handoff = Path(directory) / "handoff.json"
            handoff.write_text(json.dumps({"short_id": "short1"}))
            result = preflight(root=directory, handoff_path=handoff)
            self.assertEqual(result["preflight_mode"],
                             "READ_ONLY_NO_NETWORK_NO_UPLOAD")
            self.assertFalse(result["model_inference_executed"])
            self.assertFalse(result["mac_pi_hardware_verified"])
            self.assertFalse(result["youtube_upload_authorized"])
            self.assertEqual(result["blockers"],
                             ["audio_independent_review_missing"])
