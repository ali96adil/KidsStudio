"""M66 black-box CLI acceptance: exit codes and machine-readable evidence.

Runs the real CLI in child processes with no mocked validators, OAuth,
network or YouTube credentials. Uses disposable local files only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kidsstudio.youtube_private_upload import UploadJournal


class OfflineAcceptanceCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mp4 = self.root / "episode_qa_master.mp4"
        self.mp4.write_bytes(b"synthetic-mp4-test-bytes" * 100)
        self.sha = hashlib.sha256(self.mp4.read_bytes()).hexdigest()
        self.journal = self.root / "upload.sqlite"
        self.job = "a" * 32

    def run_cli(self, *extra):
        env = os.environ.copy()
        env.pop("KIDSSTUDIO_PI_YT_REFRESH_TOKEN", None)
        env.pop("KIDSSTUDIO_PI_YT_CLIENT_SECRET", None)
        return subprocess.run(
            [sys.executable, "-m", "kidsstudio.m66_offline_acceptance",
             "--mp4", str(self.mp4), "--expected-sha256", self.sha, *extra],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env, text=True, capture_output=True, timeout=20,
            check=False,
        )

    def test_good_master_emits_explicit_no_upload_receipt(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["pass"])
        self.assertFalse(receipt["network_used"])
        self.assertFalse(receipt["upload_performed"])
        self.assertFalse(receipt["public_release_authorized"])
        self.assertFalse(receipt["field_youtube_upload_verified"])

    def test_bad_digest_returns_nonzero(self):
        self.mp4.write_bytes(b"tampered-test-media" * 100)
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)["pass"])

    def test_missing_reservation_fails_closed(self):
        UploadJournal(self.journal)
        result = self.run_cli("--journal", str(self.journal),
                              "--job", self.job)
        self.assertEqual(result.returncode, 2)
        self.assertIn("BLOCKED", result.stderr)

    def test_valid_reservation_reports_state_without_upload(self):
        UploadJournal(self.journal).reserve(self.job, self.sha, "b" * 64)
        result = self.run_cli("--journal", str(self.journal),
                              "--job", self.job)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["reserved"]["journal_state"], "STARTED")
        self.assertFalse(receipt["upload_performed"])

    def test_incomplete_journal_options_fail_closed(self):
        result = self.run_cli("--journal", str(self.journal))
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
