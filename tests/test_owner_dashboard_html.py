import unittest

from kidsstudio.owner_dashboard_html import render


class DashboardHtmlTests(unittest.TestCase):
    def sample(self):
        return {
            "paused": False,
            "counts": {"QUEUED": 1, "FAILED": 0},
            "attention": {"failed_in_recent_window": 0},
            "recent_window": {"truncated": False},
            "recent_jobs": [],
        }

    def test_empty_state_and_no_external_scripts(self):
        page = render(self.sample())
        self.assertIn("No jobs yet", page)
        self.assertIn("read-only offline snapshot", page)
        self.assertNotIn("<script", page)
        self.assertIn("default-src 'none'", page)

    def test_escapes_untrusted_metadata(self):
        data = self.sample()
        data["recent_jobs"] = [{
            "job_id": '<img src=x onerror=alert(1)>',
            "kind": "script_draft",
            "state": "QUEUED",
            "attempts": 1,
        }]
        page = render(data)
        self.assertNotIn('<img src=x onerror=alert(1)>', page)
        self.assertIn("&lt;img", page)

    def test_truncation_warning(self):
        data = self.sample()
        data["recent_window"]["truncated"] = True
        self.assertIn("not all jobs", render(data))


if __name__ == "__main__":
    unittest.main()
