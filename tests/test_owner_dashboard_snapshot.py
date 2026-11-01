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
            self.assertEqual(result["recent_jobs"], [])
            self.assertIn("QUEUED", result["counts"])
            self.assertNotIn("database", result)

    def test_rejects_invalid_limit(self):
        for value in (0, 101, True, "5", -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    snapshot("/tmp/does-not-exist.sqlite", value)


if __name__ == "__main__":
    unittest.main()
