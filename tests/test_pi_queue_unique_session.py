import sqlite3
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_upload_queue import PiUploadQueue


class UniqueSessionQueueTests(unittest.TestCase):
    def test_enqueue_same_session_returns_original_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = PiUploadQueue(Path(tmp) / "queue.sqlite")
            queue.initialize()
            session = Path(tmp) / "session.json"
            first = queue.enqueue("red-ar", session, "channel")
            self.assertEqual(queue.enqueue("red-ar", session, "channel"), first)
            claimed = queue.claim()
            queue.finish(claimed["id"], success=True)
            self.assertEqual(queue.enqueue("red-ar", session, "channel"), first)
            with sqlite3.connect(queue.path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pi_upload_jobs").fetchone()[0], 1)

    def test_mismatched_episode_or_channel_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = PiUploadQueue(Path(tmp) / "queue.sqlite")
            queue.initialize()
            session = Path(tmp) / "session.json"
            queue.enqueue("red-ar", session, "channel-a")
            with self.assertRaises(ValueError):
                queue.enqueue("blue-ar", session, "channel-a")
            with self.assertRaises(ValueError):
                queue.enqueue("red-ar", session, "channel-b")

    def test_existing_duplicates_fail_closed_on_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.sqlite"
            queue = PiUploadQueue(path)
            queue.initialize()
            with sqlite3.connect(queue.path) as db:
                db.execute("DROP INDEX idx_pi_jobs_session_unique")
            queue.enqueue("red-ar", "/tmp/session.json", "channel")
            with sqlite3.connect(queue.path) as db:
                db.execute(
                    "INSERT INTO pi_upload_jobs (episode_id,session_path,channel_id,state,"
                    "created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    ("red-ar", "/tmp/session.json", "channel", "failed", "now", "now"),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                queue.initialize()


if __name__ == "__main__":
    unittest.main()
