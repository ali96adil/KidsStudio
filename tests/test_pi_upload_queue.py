import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_worker import process_one


class PiQueueTests(unittest.TestCase):
    def test_persists_and_recovers_after_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "queue.db"
            queue = PiUploadQueue(path)
            queue.initialize()
            job_id = queue.enqueue("red-ar", "/tmp/upload-session.json", "channel")
            claimed = queue.claim()
            self.assertEqual(claimed["id"], job_id)
            self.assertIsNone(queue.claim())
            reopened = PiUploadQueue(path)
            self.assertEqual(reopened.recover_interrupted(), 1)
            self.assertEqual(reopened.claim()["id"], job_id)
            reopened.finish(job_id, success=True)
            self.assertIsNone(reopened.claim())

    def test_worker_processes_one(self):
        with tempfile.TemporaryDirectory() as root:
            queue = PiUploadQueue(Path(root) / "queue.db")
            queue.initialize()
            session = Path(root) / "session.json"
            session.write_text("mocked session")
            queue.enqueue("red", session, "channel")
            with patch("kidsstudio.pi_upload_worker.supervise_resume",
                       return_value={"recorded_private_upload": True}) as supervisor:
                result = process_one(queue, object(), lambda: "token")
            self.assertEqual(result["episode_id"], "red")
            self.assertEqual(supervisor.call_count, 1)
            self.assertIsNone(queue.claim())

    def test_worker_failure_does_not_retry_automatically(self):
        with tempfile.TemporaryDirectory() as root:
            queue = PiUploadQueue(Path(root) / "queue.db")
            queue.initialize()
            session = Path(root) / "session.json"
            session.write_text("mocked session")
            queue.enqueue("red", session, "channel")
            with patch("kidsstudio.pi_upload_worker.supervise_resume", side_effect=RuntimeError("secret")):
                with self.assertRaises(RuntimeError):
                    process_one(queue, object(), lambda: "token")
            self.assertIsNone(queue.claim())
            self.assertEqual(queue.recover_interrupted(), 0)


if __name__ == "__main__":
    unittest.main()
