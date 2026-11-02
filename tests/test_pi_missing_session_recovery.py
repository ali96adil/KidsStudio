import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_missing_session_recovery import missing_session_actions
from kidsstudio.pi_upload_queue import PiUploadQueue


class MissingSessionRecoveryTests(unittest.TestCase):
    def test_missing_session_requires_manual_reconciliation(self):
        with tempfile.TemporaryDirectory() as root:
            queue = PiUploadQueue(Path(root) / "queue.sqlite")
            queue.initialize()
            job_id = queue.enqueue(
                "colors-red-ar", Path(root) / "missing-secret-session.json", "channel"
            )
            actions = missing_session_actions(queue)
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["job_id"], job_id)
            self.assertEqual(actions[0]["action"], "manual_reconcile_youtube_before_retry")
            self.assertFalse(actions[0]["automatic_retry_allowed"])
            self.assertFalse(actions[0]["new_upload_allowed"])
            self.assertNotIn("missing-secret-session", str(actions))
            self.assertIsNotNone(queue.claim())  # report did not modify queue

    def test_no_actions_for_empty_queue(self):
        with tempfile.TemporaryDirectory() as root:
            queue = PiUploadQueue(Path(root) / "queue.sqlite")
            queue.initialize()
            self.assertEqual(missing_session_actions(queue), [])


if __name__ == "__main__":
    unittest.main()
