"""M66 real subprocess lock acceptance on the host OS.

Two distinct Python processes contend for the same Pi uploader lock.
No Pi, YouTube, OAuth, credentials or media are touched.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kidsstudio.m66_pi_runner_lock import ExclusiveUploaderLock


class RunnerSubprocessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal = Path(self.tmp.name) / "journal.sqlite"

    def _child(self):
        code = (
            "from pathlib import Path\n"
            "from kidsstudio.m66_pi_runner_lock import ExclusiveUploaderLock, UploaderAlreadyRunning\n"
            "import sys\n"
            "try:\n"
            "    with ExclusiveUploaderLock(Path(sys.argv[1])): print('ACQUIRED')\n"
            "except UploaderAlreadyRunning:\n"
            "    print('BLOCKED')\n"
        )
        return subprocess.run(
            [sys.executable, "-c", code, str(self.journal)],
            capture_output=True, text=True, timeout=15,
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=True,
        ).stdout.strip()

    def test_second_process_blocked_while_parent_holds_lock(self):
        with ExclusiveUploaderLock(self.journal):
            self.assertEqual(self._child(), "BLOCKED")

    def test_second_process_allowed_after_parent_releases(self):
        with ExclusiveUploaderLock(self.journal):
            pass
        self.assertEqual(self._child(), "ACQUIRED")

    def test_lock_persists_as_file_but_not_as_stale_lease(self):
        with ExclusiveUploaderLock(self.journal):
            pass
        self.assertTrue(Path(str(self.journal) + ".runner.lock").exists())
        self.assertEqual(self._child(), "ACQUIRED")


if __name__ == "__main__":
    unittest.main()
