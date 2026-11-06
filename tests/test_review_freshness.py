import unittest

from kidsstudio.review_freshness import project_review_freshness

A = "a" * 64
B = "b" * 64


class ReviewFreshnessTests(unittest.TestCase):
    def project(self, reviews, sha=A):
        return project_review_freshness(reviews, current_video_sha256=sha)

    def test_no_review(self):
        self.assertEqual(self.project([])["status"], "NO_REVIEW")

    def test_matching_private_accepted_is_not_public_approval(self):
        report = self.project([{"review_id": 1, "video_sha256": A,
                                "review_outcome": "ACCEPTED_PRIVATE"}])
        self.assertEqual(report["status"], "CURRENT_VERSION_ACCEPTED_PRIVATE_ONLY")
        self.assertFalse(report["owner_publication_approval"])

    def test_old_version_is_stale(self):
        report = self.project([{"review_id": 1, "video_sha256": A,
                                "review_outcome": "ACCEPTED_PRIVATE"}], B)
        self.assertEqual(report["status"], "LATEST_REVIEW_STALE")

    def test_latest_review_wins(self):
        report = self.project([
            {"review_id": 2, "video_sha256": B, "review_outcome": "REVISION_REQUIRED"},
            {"review_id": 1, "video_sha256": A, "review_outcome": "ACCEPTED_PRIVATE"},
        ], B)
        self.assertEqual(report["status"], "CURRENT_VERSION_REVISION_REQUIRED")

    def test_review_pending(self):
        report = self.project([{"review_id": 1, "video_sha256": A,
                                "review_outcome": "NEEDS_REVIEW"}])
        self.assertEqual(report["status"], "CURRENT_VERSION_NEEDS_REVIEW")

    def test_duplicate_review_id_rejected(self):
        with self.assertRaises(ValueError):
            self.project([{"review_id": 1, "video_sha256": A,
                           "review_outcome": "NEEDS_REVIEW"}] * 2)

    def test_bad_sha_rejected(self):
        with self.assertRaises(ValueError):
            self.project([], "invalid")

    def test_invalid_outcome_rejected(self):
        with self.assertRaises(ValueError):
            self.project([{"review_id": 1, "video_sha256": A,
                           "review_outcome": "PUBLISHED"}])


if __name__ == "__main__":
    unittest.main()
