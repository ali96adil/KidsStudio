import sqlite3
import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_episode_status import episode_statuses
from kidsstudio.owner_unified_dashboard import render_unified
from kidsstudio.pi_upload_queue import PiUploadQueue


class EpisodeStatusTests(unittest.TestCase):
    def test_latest_upload_state_and_review_priority(self):
        with tempfile.TemporaryDirectory() as root:
            queue = PiUploadQueue(Path(root) / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red", "/tmp/old.json", "channel")
            queue.enqueue("red", "/tmp/new.json", "channel")
            with sqlite3.connect(queue.path) as db:
                db.execute("UPDATE pi_upload_jobs SET state='failed' WHERE id=1")
                db.execute("UPDATE pi_upload_jobs SET state='completed' WHERE id=2")
            series = {"series": [{"title": "Colors", "episodes": [
                {"id": "red", "title": "<unsafe>", "stage": "editing"},
                {"id": "blue", "title": "Blue", "stage": "script"},
            ]}]}
            rows = episode_statuses(series, {"red": {"state": "needs_review"}}, queue.path)
            self.assertEqual(rows[0]["upload_state"], "completed")
            self.assertEqual(rows[0]["next_step"], "owner_review")
            self.assertEqual(rows[1]["upload_state"], "not_started")
            production = {
                "paused": False, "counts": {}, "recent_jobs": [],
                "attention": {"failed_in_recent_window": 0},
                "recent_window": {"truncated": False},
            }
            full_series = {"episode_count": 2, "series": [{
                **series["series"][0], "episode_count": 2,
                "stage_counts": {"editing": 1, "script": 1},
            }]}
            uploads = {"queue": {"pending": 0, "running": 0, "completed": 1, "failed": 1},
                       "sessions": {"counts": {"corrupt": 0, "orphaned": 0}}}
            html = render_unified(production, full_series, {}, uploads, rows)
            self.assertIn("Episode progress", html)
            self.assertIn("&lt;unsafe&gt;", html)
            self.assertNotIn("<unsafe>", html)
            self.assertIn("owner_review", html)


if __name__ == "__main__":
    unittest.main()
