import unittest

from kidsstudio.owner_unified_dashboard import render_unified


class UnifiedDashboardTests(unittest.TestCase):
    def test_private_upload_metrics_are_in_combined_owner_page(self):
        production = {
            "paused": False, "counts": {"QUEUED": 1},
            "recent_jobs": [],
            "attention": {"failed_in_recent_window": 0},
            "recent_window": {"truncated": False},
        }
        series = {"episode_count": 1, "series": [{
            "title": "Colors", "episode_count": 1,
            "stage_counts": {"script": 1},
            "episodes": [{"id": "red", "title": "Red", "stage": "script"}],
        }]}
        uploads = {
            "queue": {"pending": 2, "running": 0, "completed": 1, "failed": 1},
            "sessions": {"counts": {"corrupt": 1, "orphaned": 0}},
        }
        html = render_unified(production, series, {}, uploads)
        self.assertIn("Private YouTube uploads", html)
        self.assertIn("Upload failures", html)
        self.assertIn("Corrupt sessions", html)
        self.assertIn("Colors", html)
        self.assertIn("Red", html)
        self.assertIn("private upload only", html)
        self.assertNotIn("<script", html.lower())


if __name__ == "__main__":
    unittest.main()
