import json
import stat
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_hardware_acceptance import main


class HardwareAcceptanceReportSecurityTests(unittest.TestCase):
    def test_private_report_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence.json"
            report = Path(tmp) / "report.json"
            self.assertEqual(main(["--init", str(evidence)]), 0)
            self.assertEqual(main(["--evidence", str(evidence), "--out", str(report)]), 2)
            self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)
            data = json.loads(report.read_text())
            self.assertEqual(len(data["remaining_steps"]), 7)
            with self.assertRaises(FileExistsError):
                main(["--evidence", str(evidence), "--out", str(report)])

    def test_symlink_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence.json"
            target = Path(tmp) / "target.json"
            target.write_text("do not change")
            link = Path(tmp) / "link.json"
            link.symlink_to(target)
            main(["--init", str(evidence)])
            with self.assertRaises(OSError):
                main(["--evidence", str(evidence), "--out", str(link)])
            self.assertEqual(target.read_text(), "do not change")


if __name__ == "__main__":
    unittest.main()
