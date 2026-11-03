import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_hardware_acceptance import main, evaluate_evidence, REQUIRED_STEPS


class HardwareAcceptanceExtraFieldsTests(unittest.TestCase):
    def test_unknown_top_level_field_rejected(self):
        evidence = {"version": 1,
                    "steps": {name: "not_tested" for name in REQUIRED_STEPS},
                    "youtube_access_token": "must-not-persist"}
        with self.assertRaises(ValueError):
            evaluate_evidence(evidence)

    def test_update_does_not_persist_unexpected_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            data = {"version": 1,
                    "steps": {name: "not_tested" for name in REQUIRED_STEPS},
                    "private_session_url": "sensitive"}
            path.write_text(json.dumps(data))
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                main(["--evidence", str(path), "--step", "mac_video_export",
                      "--status", "pass"])
            self.assertEqual(json.loads(path.read_text()), data)


if __name__ == "__main__":
    unittest.main()
