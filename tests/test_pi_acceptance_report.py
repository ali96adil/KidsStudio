import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_acceptance_report import build_acceptance_report, main


class PiAcceptanceReportTests(unittest.TestCase):
    def test_report_never_claims_live_upload(self):
        report = build_acceptance_report()
        self.assertTrue(report["passed"], report)
        self.assertTrue(all(report["checks"].values()))
        self.assertFalse(report["evidence"]["youtube_upload_tested"])
        self.assertFalse(report["evidence"]["mac_to_pi_transfer_tested"])
        self.assertFalse(report["evidence"]["owner_review_tested"])
        self.assertFalse(report["evidence"]["public_release_enabled"])
        self.assertEqual(report["next_action"], "run_private_hardware_acceptance")

    def test_report_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "acceptance.json"
            with patch("sys.argv", ["pi_acceptance_report", "--out", str(output)]):
                self.assertEqual(main(), 0)
                with self.assertRaises(FileExistsError):
                    main()


if __name__ == "__main__":
    unittest.main()
