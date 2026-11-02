import unittest

from kidsstudio.pi_upload_dashboard import render_upload_dashboard
from kidsstudio.owner_unified_dashboard import render_unified


class MissingSessionDashboardTests(unittest.TestCase):
    def test_pi_dashboard_shows_missing_session_metric(self):
        data = {
            "queue": {"pending": 1, "running": 0, "completed": 0, "failed": 0},
            "sessions": {"healthy": False, "counts": {
                "corrupt": 0, "orphaned": 0, "missing": 2,
            }},
        }
        page = render_upload_dashboard(data)
        self.assertIn("Missing sessions", page)
        self.assertIn("Attention required", page)

    def test_unified_dashboard_shows_missing_session_metric(self):
        from unittest.mock import patch
        with patch("kidsstudio.owner_unified_dashboard.render_combined",
                   return_value="<html><footer>Local snapshot only.</footer></html>"):
            page = render_unified(
                {}, {}, {},
                {"queue": {"pending": 0, "running": 0, "completed": 0, "failed": 0},
                 "sessions": {"counts": {
                     "corrupt": 0, "orphaned": 0, "missing": 3,
                 }}},
            )
        self.assertIn("Missing sessions", page)
        self.assertIn("<strong>3</strong>", page)


if __name__ == "__main__":
    unittest.main()
