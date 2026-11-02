import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kidsstudio.pi_upload_queue import PiUploadQueue


class PiQueueConcurrencyTests(unittest.TestCase):
    def test_concurrent_enqueue_same_session_creates_one_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.sqlite"
            PiUploadQueue(path).initialize()
            session = Path(tmp) / "session.json"
            barrier = threading.Barrier(8)

            def enqueue(_):
                queue = PiUploadQueue(path)
                barrier.wait(timeout=10)
                return queue.enqueue("red-ar", session, "channel")

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(enqueue, range(8)))
            self.assertEqual(len(set(results)), 1)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pi_upload_jobs").fetchone()[0], 1)

    def test_concurrent_claims_do_not_share_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.sqlite"
            queue = PiUploadQueue(path)
            queue.initialize()
            for n in range(12):
                queue.enqueue(f"red-{n}", Path(tmp) / f"{n}.json", "channel")
            barrier = threading.Barrier(8)

            def claim(_):
                barrier.wait(timeout=10)
                return PiUploadQueue(path).claim()

            with ThreadPoolExecutor(max_workers=8) as pool:
                jobs = list(pool.map(claim, range(8)))
            self.assertTrue(all(job is not None for job in jobs))
            self.assertEqual(len({job["id"] for job in jobs}), 8)
            with sqlite3.connect(path) as db:
                states = dict(db.execute(
                    "SELECT state,COUNT(*) FROM pi_upload_jobs GROUP BY state"
                ).fetchall())
            self.assertEqual(states["running"], 8)
            self.assertEqual(states["pending"], 4)

    def test_mismatched_channel_race_never_rebinds_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.sqlite"
            PiUploadQueue(path).initialize()
            session = Path(tmp) / "session.json"
            barrier = threading.Barrier(2)

            def enqueue(channel):
                barrier.wait(timeout=10)
                try:
                    return PiUploadQueue(path).enqueue("red-ar", session, channel)
                except ValueError:
                    return None

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(enqueue, ("channel-a", "channel-b")))
            self.assertEqual(sum(value is not None for value in results), 1)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pi_upload_jobs").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
