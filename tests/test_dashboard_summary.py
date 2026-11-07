import unittest

from kidsstudio.dashboard_summary import build_dashboard_summary


class DashboardSummaryTests(unittest.TestCase):
    def sample(self):
        return {
            "status": "READ_ONLY_QUEUE_SNAPSHOT",
            "queue_paused": False,
            "total_jobs": 8,
            "jobs_by_kind_and_state": {
                "script_draft": {
                    "QUEUED": 2, "LEASED": 1, "COMPLETED": 3,
                    "FAILED": 1, "CANCELLED": 1,
                },
            },
        }

    def test_counts_are_aggregated(self):
        result = build_dashboard_summary(self.sample())
        self.assertEqual(result["waiting"], 2)
        self.assertEqual(result["running"], 1)
        self.assertEqual(result["completed"], 3)
        self.assertEqual(result["needs_attention"], 1)
        self.assertEqual(result["cancelled"], 1)

    def test_no_publication_or_episode_inference(self):
        result = build_dashboard_summary(self.sample())
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["episode_status_available"])
        self.assertFalse(result["queue_mutated"])

    def test_mismatched_total_fails(self):
        snapshot = self.sample()
        snapshot["total_jobs"] = 999
        with self.assertRaises(ValueError):
            build_dashboard_summary(snapshot)

    def test_negative_count_fails(self):
        snapshot = self.sample()
        snapshot["jobs_by_kind_and_state"]["script_draft"]["FAILED"] = -1
        with self.assertRaises(ValueError):
            build_dashboard_summary(snapshot)

    def test_noninteger_count_fails(self):
        snapshot = self.sample()
        snapshot["jobs_by_kind_and_state"]["script_draft"]["QUEUED"] = True
        with self.assertRaises(ValueError):
            build_dashboard_summary(snapshot)

    def test_invalid_paused_fails(self):
        snapshot = self.sample()
        snapshot["queue_paused"] = "false"
        with self.assertRaises(ValueError):
            build_dashboard_summary(snapshot)


if __name__ == "__main__":
    unittest.main()
