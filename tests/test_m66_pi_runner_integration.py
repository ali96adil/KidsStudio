"""M66 integration regression: actual Pi CLI must reject duplicate runners.

No OAuth, media or Google network. A fake service substitutes the Pi poll
to prove the CLI's lock is acquired before the real poll loop is entered.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m66_pi_runner_lock import ExclusiveUploaderLock
from kidsstudio.pi_all_private_uploader import main


class PiRunnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.journal = root / "journal.sqlite"
        self.args = [
            "--db", str(root / "queue.sqlite"),
            "--inbox-root", str(root / "inbox"),
            "--journal", str(self.journal),
            "--execute",
        ]

    def test_existing_runner_lock_blocks_poll(self):
        calls = []
        with patch("kidsstudio.pi_all_private_uploader.GoogleOAuthRefresh", return_value=object()), \
             patch("kidsstudio.pi_all_private_uploader.UploadJournal", return_value=object()), \
             patch("kidsstudio.pi_all_private_uploader.PiAllPrivateUploadService") as service, \
             patch("kidsstudio.pi_all_private_uploader.StudioQueue", return_value=object()):
            service.return_value.poll_once.side_effect = lambda: calls.append("poll")
            with ExclusiveUploaderLock(self.journal):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(self.args), 2)
        self.assertEqual(calls, [])

    def test_unlocked_runner_polls_once(self):
        with patch("kidsstudio.pi_all_private_uploader.GoogleOAuthRefresh", return_value=object()), \
             patch("kidsstudio.pi_all_private_uploader.UploadJournal", return_value=object()), \
             patch("kidsstudio.pi_all_private_uploader.PiAllPrivateUploadService") as service, \
             patch("kidsstudio.pi_all_private_uploader.StudioQueue", return_value=object()):
            service.return_value.poll_once.return_value = {"status": "SYNTHETIC_PRIVATE_IDLE"}
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.args), 0)
            service.return_value.poll_once.assert_called_once_with()

    def test_released_runner_can_poll_again(self):
        with patch("kidsstudio.pi_all_private_uploader.GoogleOAuthRefresh", return_value=object()), \
             patch("kidsstudio.pi_all_private_uploader.UploadJournal", return_value=object()), \
             patch("kidsstudio.pi_all_private_uploader.PiAllPrivateUploadService") as service, \
             patch("kidsstudio.pi_all_private_uploader.StudioQueue", return_value=object()):
            service.return_value.poll_once.return_value = {"status": "SYNTHETIC_PRIVATE_IDLE"}
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.args), 0)
                self.assertEqual(main(self.args), 0)
            self.assertEqual(service.return_value.poll_once.call_count, 2)


if __name__ == "__main__":
    unittest.main()
