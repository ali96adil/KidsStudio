"""M66 real CLI lock contention between legacy and combined Pi uploaders.

Uses the production CLI entry points and production flock, with OAuth and
upload services mocked. No network or YouTube operations.
"""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m66_pi_runner_lock import ExclusiveUploaderLock
from kidsstudio import pi_all_private_uploader, pi_recovery_uploader


class CrossEntrypointLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.journal = root / "upload.sqlite"
        self.args = [
            "--db", str(root / "queue.sqlite"),
            "--inbox-root", str(root / "inbox"),
            "--journal", str(self.journal),
            "--execute",
        ]

    def test_legacy_blocked_by_combined_lock(self):
        with patch.object(pi_recovery_uploader, "GoogleOAuthRefresh", return_value=object()), \
             patch.object(pi_recovery_uploader, "StudioQueue", return_value=object()), \
             patch.object(pi_recovery_uploader, "PiMediaInbox", return_value=object()), \
             patch.object(pi_recovery_uploader, "UploadJournal", return_value=object()), \
             patch.object(pi_recovery_uploader, "PiPrivateUploadService") as service:
            with ExclusiveUploaderLock(self.journal):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(pi_recovery_uploader.main(self.args), 2)
            service.return_value.poll_once.assert_not_called()

    def test_combined_blocked_by_legacy_lock(self):
        with patch.object(pi_all_private_uploader, "GoogleOAuthRefresh", return_value=object()), \
             patch.object(pi_all_private_uploader, "StudioQueue", return_value=object()), \
             patch.object(pi_all_private_uploader, "UploadJournal", return_value=object()), \
             patch.object(pi_all_private_uploader, "PiAllPrivateUploadService") as service:
            with ExclusiveUploaderLock(self.journal):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(pi_all_private_uploader.main(self.args), 2)
            service.return_value.poll_once.assert_not_called()

    def test_legacy_can_run_after_lock_release(self):
        with patch.object(pi_recovery_uploader, "GoogleOAuthRefresh", return_value=object()), \
             patch.object(pi_recovery_uploader, "StudioQueue", return_value=object()), \
             patch.object(pi_recovery_uploader, "PiMediaInbox", return_value=object()), \
             patch.object(pi_recovery_uploader, "UploadJournal", return_value=object()), \
             patch.object(pi_recovery_uploader, "PiPrivateUploadService") as service:
            service.return_value.poll_once.return_value = {"status": "SYNTHETIC_IDLE"}
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pi_recovery_uploader.main(self.args), 0)
            service.return_value.poll_once.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
