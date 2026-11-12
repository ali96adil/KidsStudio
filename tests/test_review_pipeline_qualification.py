import unittest

from kidsstudio.review_pipeline_qualification import run_review_pipeline_qualification


class ReviewPipelineQualificationTests(unittest.TestCase):
    def test_complete_offline_review_pipeline(self):
        report = run_review_pipeline_qualification()
        self.assertEqual(report["status"], "OFFLINE_REVIEW_PIPELINE_PASS")
        self.assertTrue(report["synthetic_video_only"])
        self.assertEqual(len(report["checks"]), 7)
        self.assertFalse(report["owner_publication_approval"])
        self.assertEqual(report["real_mac_pi_qualification"], "NOT_RUN")

    def test_repeatable_isolated_runs(self):
        first = run_review_pipeline_qualification()
        second = run_review_pipeline_qualification()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
