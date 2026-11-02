import unittest

from kidsstudio.pi_offline_trial import run_offline_trial


class OfflinePiTrialTests(unittest.TestCase):
    def test_first_run_and_readiness_are_healthy(self):
        result = run_offline_trial()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["first_boot_exit_code"], 0)
        self.assertEqual(result["tick_invocations"], 1)
        self.assertTrue(result["readiness"]["checks"]["upload_queue_readable"])
        self.assertTrue(result["readiness"]["checks"]["sessions_healthy"])
        self.assertTrue(result["offline_only"])
        self.assertFalse(result["youtube_upload_tested"])
        self.assertFalse(result["public_release_enabled"])


if __name__ == "__main__":
    unittest.main()
