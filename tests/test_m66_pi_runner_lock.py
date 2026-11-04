"""M66 Pi single-instance lock tests; no Pi or YouTube required."""
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m66_pi_runner_lock import ExclusiveUploaderLock, UploaderAlreadyRunning


class RunnerLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = Path(self.temp.name) / "journal.sqlite"

    def test_second_runner_blocked(self):
        with ExclusiveUploaderLock(self.journal):
            with self.assertRaises(UploaderAlreadyRunning):
                with ExclusiveUploaderLock(self.journal):
                    pass

    def test_lock_released_on_exit(self):
        with ExclusiveUploaderLock(self.journal):
            pass
        with ExclusiveUploaderLock(self.journal):
            pass

    def test_lock_released_on_exception(self):
        with self.assertRaises(ValueError):
            with ExclusiveUploaderLock(self.journal):
                raise ValueError("simulated crash")
        with ExclusiveUploaderLock(self.journal):
            pass

    def test_symlink_lock_rejected(self):
        target = Path(self.temp.name) / "target"
        target.write_text("untouched")
        Path(str(self.journal) + ".runner.lock").symlink_to(target)
        with self.assertRaises(UploaderAlreadyRunning):
            with ExclusiveUploaderLock(self.journal):
                pass
        self.assertEqual(target.read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()
