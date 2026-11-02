import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kidsstudio.pi_missing_session_recovery import missing_session_actions
from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_worker import process_one


class InvalidSessionWorkerTests(unittest.TestCase):
    def test_invalid_session_fails_closed_without_oauth(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            session = base / "session.json"
            session.write_text("invalid session")
            session.chmod(0o600)
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            job_id = queue.enqueue("colors-red-ar", session, "channel")
            token = Mock(side_effect=AssertionError("OAuth must not be called"))
            with patch("kidsstudio.pi_upload_worker.supervise_resume") as resume:
                result = process_one(queue, object(), token)
            self.assertEqual(result["result"], "manual_reconcile_youtube_before_retry")
            token.assert_not_called()
            resume.assert_not_called()
            with sqlite3.connect(queue.path) as db:
                state = db.execute(
                    "SELECT state FROM pi_upload_jobs WHERE id=?", (job_id,)
                ).fetchone()[0]
            self.assertEqual(state, "failed")
            self.assertIsNone(queue.claim())
            actions = missing_session_actions(queue)
            self.assertEqual(actions[0]["reason"], "resumable_session_invalid")
            self.assertFalse(actions[0]["new_upload_allowed"])


if __name__ == "__main__":
    unittest.main()
