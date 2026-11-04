"""M66: both Pi upload entry points must share one journal lock.

Static regression guard: this test does not create Google credentials,
touch the Pi, or run a real uploader.
"""
import inspect
import unittest

from kidsstudio import pi_all_private_uploader, pi_recovery_uploader
from kidsstudio.m66_pi_runner_lock import ExclusiveUploaderLock


class SharedPiUploaderLockTests(unittest.TestCase):
    def test_combined_and_legacy_use_same_lock(self):
        for module in (pi_all_private_uploader, pi_recovery_uploader):
            with self.subTest(module=module.__name__):
                self.assertIs(module.ExclusiveUploaderLock, ExclusiveUploaderLock)
                source = inspect.getsource(module.main)
                self.assertIn("with ExclusiveUploaderLock(args.journal):", source)
                self.assertIn("service.poll_once()", source)
                self.assertLess(
                    source.index("with ExclusiveUploaderLock(args.journal):"),
                    source.index("service.poll_once()"),
                )

    def test_legacy_has_no_upload_in_dry_run(self):
        self.assertEqual(
            pi_recovery_uploader.main([
                "--db", "/unused/studio.sqlite",
                "--inbox-root", "/unused/media",
                "--journal", "/unused/upload.sqlite",
            ]),
            0,
        )


if __name__ == "__main__":
    unittest.main()
