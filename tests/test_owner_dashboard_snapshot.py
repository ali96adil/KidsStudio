import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_dashboard_snapshot import snapshot
from kidsstudio.studio_queue import StudioQueue


class OwnerDashboardSnapshotTests(unittest.TestCase):
    def test_empty_queue_is_read_only_and_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "studio.sqlite"
            StudioQueue(db).initialize()
            result = snapshot(db)
            self.assertTrue(result["read_only"])
            self.assertEqual(result["schema_version"], 2)
            self.assertEqual(result["recent_jobs"], [])
            self.assertEqual(result["attention"]["failed_in_recent_window"], 0)
            self.assertFalse(result["recent_window"]["truncated"])
            self.assertIn("QUEUED", result["counts"])
            self.assertNotIn("database", result)

    def test_job_summary_excludes_private_payload(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "studio.sqlite"
            queue = StudioQueue(db)
            queue.initialize()
            queue.enqueue(kind="script_draft", request_key="dashboard-test-1",
                          payload={"prompt": "PRIVATE STORY MATERIAL"})
            result = snapshot(db)
            self.assertEqual(result["recent_window"]["by_kind"]["script_draft"], 1)
            self.assertEqual(result["recent_window"]["by_kind_and_state"]["script_draft"]["QUEUED"], 1)
            self.assertEqual(result["recent_window"]["returned"], 1)
            self.assertNotIn("PRIVATE STORY MATERIAL", str(result))
            self.assertNotIn("payload", result["recent_jobs"][0])

    def test_truncation_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "studio.sqlite"
            queue = StudioQueue(db)
            queue.initialize()
            for i in range(3):
                queue.enqueue(kind="script_draft", request_key=f"dashboard-{i}", payload={})
            result = snapshot(db, limit=1)
            self.assertTrue(result["recent_window"]["truncated"])
            self.assertEqual(result["recent_window"]["returned"], 1)
            self.assertEqual(result["counts"]["QUEUED"], 3)

    def test_rejects_invalid_limit(self):
        for value in (0, 101, True, "5", -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    snapshot("/tmp/does-not-exist.sqlite", value)


if __name__ == "__main__":
    unittest.main()
