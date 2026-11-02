import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_worker import process_one


class WorkerMissingSessionGuardTests(unittest.TestCase):
    def test_missing_session_never_invokes_resume_or_token(self):
        with tempfile.TemporaryDirectory() as root:
            queue = PiUploadQueue(Path(root) / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red-ar", Path(root) / "absent.json", "channel")
            with patch("kidsstudio.pi_upload_worker.supervise_resume") as resume:
                result = process_one(
                    queue, object(),
                    lambda: self.fail("OAuth must not be used"),
                )
            resume.assert_not_called()
            self.assertEqual(result["result"], "manual_reconcile_youtube_before_retry")
            self.assertIsNone(queue.claim())
            self.assertEqual(missing_state(queue), "failed")


def missing_state(queue):
    import sqlite3
    with sqlite3.connect(queue.path) as db:
        return db.execute("SELECT state FROM pi_upload_jobs LIMIT 1").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
