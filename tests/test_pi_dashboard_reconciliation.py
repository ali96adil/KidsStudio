import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_dashboard import upload_snapshot, render_upload_dashboard
from kidsstudio.owner_unified_dashboard import render_unified


class DashboardReconciliationTests(unittest.TestCase):
    def test_missing_session_requires_review_in_pi_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir()
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red-ar", sessions / "missing.json", "channel")
            data = upload_snapshot(queue, sessions)
            self.assertEqual(data["reconciliation"]["episodes"][0]["action"],
                             "manual_reconcile_youtube_before_retry")
            html = render_upload_dashboard(data)
            self.assertIn("Sessions requiring review", html)
            self.assertIn("Attention required", html)
            self.assertNotIn(str(root), html)

    def test_unified_render_handles_existing_snapshot_without_reconciliation(self):
        # Older saved snapshots must remain renderable.
        from unittest.mock import patch
        uploads = {
            "queue": {"pending": 0, "running": 0, "completed": 0, "failed": 0},
            "sessions": {"counts": {"corrupt": 0, "orphaned": 0}},
        }
        with patch("kidsstudio.owner_unified_dashboard.render_combined",
                   return_value="<html><footer>Local snapshot only.</footer></html>"):
            html = render_unified({}, {}, {}, uploads)
        self.assertIn("Sessions requiring review", html)
        self.assertIn("Private YouTube uploads", html)


if __name__ == "__main__":
    unittest.main()
