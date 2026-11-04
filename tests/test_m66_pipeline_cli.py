"""Exercise the actual M66 CLIs together using a real SQLite journal.

No Pi, network, OAuth, or YouTube access is needed.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kidsstudio.youtube_private_upload import UploadJournal


class M66PipelineCLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", *args],
            text=True, capture_output=True, timeout=20,
        )

    def test_unresolved_reservation_blocks_bundle_even_with_stable_reboot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mp4 = root / "master.mp4"
            mp4.write_bytes(b"m66-integrated-test-content" * 100)
            sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
            journal = root / "uploads.sqlite"
            job = "a" * 32
            UploadJournal(journal).reserve(job, sha, "b" * 64)

            accepted = self.run_cli(
                "kidsstudio.m66_offline_acceptance", "--mp4", str(mp4),
                "--expected-sha256", sha, "--journal", str(journal),
                "--job", job,
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            acceptance = json.loads(accepted.stdout)
            self.assertEqual(acceptance["reserved"]["master_sha256"], sha)
            self.assertFalse(acceptance["field_youtube_upload_verified"])
            (root / "acceptance.json").write_text(accepted.stdout)

            for name in ("before", "after"):
                result = self.run_cli(
                    "kidsstudio.m66_journal_report", "--journal", str(journal))
                self.assertEqual(result.returncode, 0, result.stderr)
                (root / (name + ".json")).write_text(result.stdout)

            stable = self.run_cli(
                "kidsstudio.m66_reboot_compare",
                "--before", str(root / "before.json"),
                "--after", str(root / "after.json"))
            self.assertEqual(stable.returncode, 0, stable.stderr)
            self.assertTrue(json.loads(stable.stdout)["pass"])

            bundle = self.run_cli(
                "kidsstudio.m66_evidence_summary",
                "--acceptance", str(root / "acceptance.json"),
                "--before", str(root / "before.json"),
                "--after", str(root / "after.json"))
            self.assertEqual(bundle.returncode, 2, bundle.stderr)
            report = json.loads(bundle.stdout)
            self.assertFalse(report["pass"])
            self.assertFalse(report["field_qualified"])
            self.assertEqual(report["journal_requires_manual_reconciliation"],
                             [job])
            self.assertFalse(report["public_release_authorized"])


if __name__ == "__main__":
    unittest.main()
