import json
import stat
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_hardware_acceptance import main, REQUIRED_STEPS


class HardwareAcceptanceStepUpdateTests(unittest.TestCase):
    def test_single_step_update_keeps_other_steps_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            self.assertEqual(main(["--init", str(path)]), 0)
            self.assertEqual(main([
                "--evidence", str(path), "--step", "mac_video_export",
                "--status", "pass",
            ]), 0)
            data = json.loads(path.read_text())
            self.assertEqual(data["steps"]["mac_video_export"], "pass")
            self.assertTrue(all(data["steps"][name] == "not_tested"
                                for name in REQUIRED_STEPS if name != "mac_video_export"))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(main(["--evidence", str(path)]), 2)

    def test_reject_incomplete_step_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.json"
            main(["--init", str(path)])
            with self.assertRaises(SystemExit):
                main(["--evidence", str(path), "--step", "mac_video_export"])
            self.assertEqual(json.loads(path.read_text())["steps"]["mac_video_export"],
                             "not_tested")


if __name__ == "__main__":
    unittest.main()
