import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.queue_dashboard import queue_dashboard_snapshot
from kidsstudio.studio_queue import StudioQueue


class QueueDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "studio.sqlite"
        self.queue = StudioQueue(self.db)
        self.queue.initialize()

    def test_empty_queue_snapshot(self):
        report = queue_dashboard_snapshot(self.db)
        self.assertEqual(report["total_jobs"], 0)
        self.assertFalse(report["episode_lifecycle_inferred"])
        self.assertFalse(report["queue_mutated"])

    def test_snapshot_does_not_change_database_bytes(self):
        before = self.db.read_bytes()
        report = queue_dashboard_snapshot(self.db)
        self.assertEqual(report["status"], "READ_ONLY_QUEUE_SNAPSHOT")
        self.assertEqual(self.db.read_bytes(), before)

    def test_snapshot_excludes_payload_and_paths(self):
        report = queue_dashboard_snapshot(self.db)
        rendered = json.dumps(report)
        self.assertNotIn(str(self.db), rendered)
        self.assertNotIn("payload", rendered)

    def test_missing_db_rejected(self):
        with self.assertRaises((OSError, ValueError)):
            queue_dashboard_snapshot(self.db.with_name("missing.sqlite"))

    def test_nonqueue_db_rejected(self):
        import sqlite3
        other = Path(self.temp.name) / "other.sqlite"
        with sqlite3.connect(other) as db:
            db.execute("CREATE TABLE unrelated(x)")
        with self.assertRaises(ValueError):
            queue_dashboard_snapshot(other)


if __name__ == "__main__":
    unittest.main()
