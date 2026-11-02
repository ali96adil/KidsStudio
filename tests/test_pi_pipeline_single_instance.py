import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_pipeline_service import run_pipeline
from kidsstudio.pi_upload_queue import PiUploadQueue


class PipelineSingleInstanceTests(unittest.TestCase):
    def test_existing_worker_lock_prevents_second_pipeline_and_recovery(self):
        import fcntl
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir(mode=0o700)
            queue = PiUploadQueue(state / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red-ar", state / "session.json", "channel")
            running = queue.claim()
            credentials = Path(tmp) / "credentials.json"
            credentials.write_text(json.dumps({"client_id": "x", "client_secret": "x",
                                               "refresh_token": "x", "channel_id": "channel"}))
            credentials.chmod(0o600)
            titles = Path(tmp) / "titles.json"
            titles.write_text("{}")
            fd = os.open(state / "worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch("kidsstudio.pi_pipeline_service.pipeline_tick") as tick:
                    self.assertEqual(run_pipeline(state_dir=state, credentials=credentials,
                                                  titles_file=titles, once=True), 2)
                    tick.assert_not_called()
                # A blocked second process must not requeue the active upload.
                self.assertIsNone(queue.claim())
                import sqlite3
                with sqlite3.connect(queue.path) as db:
                    self.assertEqual(db.execute("SELECT state FROM pi_upload_jobs WHERE id=?",
                                                (running["id"],)).fetchone()[0], "running")
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
