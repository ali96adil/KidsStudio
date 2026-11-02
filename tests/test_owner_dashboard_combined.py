import unittest

from kidsstudio.owner_dashboard_combined import render_combined
from kidsstudio.owner_series_board import summarize


class CombinedDashboardTests(unittest.TestCase):
    def test_series_and_queue_visible(self):
        queue = {
            "paused": False, "counts": {"QUEUED": 1},
            "attention": {"failed_in_recent_window": 0},
            "recent_window": {"truncated": False},
            "recent_jobs": [],
        }
        series = summarize({"schema_version": 1, "series": [{
            "id": "colors", "title": "الألوان", "episodes": [{
                "id": "one", "title": "<script>alert(1)</script>", "stage": "script"
            }]
        }]})
        page = render_combined(queue, series)
        self.assertIn("Educational series", page)
        self.assertIn("الألوان", page)
        self.assertIn("Waiting", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_owner_review_status_visible_and_escaped(self):
        queue = {
            "paused": False, "counts": {}, "attention": {"failed_in_recent_window": 0},
            "recent_window": {"truncated": False}, "recent_jobs": [],
        }
        series = summarize({"schema_version": 1, "series": [{
            "id": "colors", "title": "Colors",
            "episodes": [{"id": "red", "title": "Red", "stage": "owner_review"}]
        }]})
        page = render_combined(queue, series, {
            "red": {"state": "changes_requested", "note": "<private>"}
        })
        self.assertIn("owner: changes_requested", page)
        self.assertNotIn("<private>", page)

    def test_empty_series(self):
        queue = {
            "paused": False, "counts": {}, "attention": {"failed_in_recent_window": 0},
            "recent_window": {"truncated": False}, "recent_jobs": [],
        }
        page = render_combined(queue, summarize({"schema_version": 1, "series": []}))
        self.assertIn("No series planned yet", page)


if __name__ == "__main__":
    unittest.main()
