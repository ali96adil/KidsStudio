import unittest

from kidsstudio.episode_lifecycle import project_episode


class EpisodeLifecycleTests(unittest.TestCase):
    def event(self, state, **kwargs):
        return dict(episode_id="colors_ar_01", state=state, **kwargs)

    def test_empty_episode_is_script_pending(self):
        report = project_episode(episode_id="colors_ar_01", events=[])
        self.assertEqual(report["state"], "SCRIPT_PENDING")
        self.assertFalse(report["queue_mutated"])

    def test_normal_private_review_path(self):
        states = ["SCRIPT_READY", "PRODUCTION_PENDING", "RENDER_READY",
                  "PRIVATE_UPLOAD_PENDING", "PRIVATE_UPLOADED",
                  "OWNER_REVIEW_PENDING"]
        report = project_episode(
            episode_id="colors_ar_01", events=[self.event(s) for s in states])
        self.assertTrue(report["requires_owner_review"])
        self.assertFalse(report["publication_performed"])

    def test_no_public_approval_without_owner(self):
        states = ["SCRIPT_READY", "PRODUCTION_PENDING", "RENDER_READY",
                  "PRIVATE_UPLOAD_PENDING", "PRIVATE_UPLOADED",
                  "OWNER_REVIEW_PENDING"]
        with self.assertRaises(ValueError):
            project_episode(episode_id="colors_ar_01",
                            events=[self.event(s) for s in states] +
                                   [self.event("PUBLICATION_APPROVED", actor="agent")])

    def test_explicit_owner_approval_is_projection_only(self):
        states = ["SCRIPT_READY", "PRODUCTION_PENDING", "RENDER_READY",
                  "PRIVATE_UPLOAD_PENDING", "PRIVATE_UPLOADED",
                  "OWNER_REVIEW_PENDING"]
        report = project_episode(
            episode_id="colors_ar_01",
            events=[self.event(s) for s in states] +
                   [self.event("PUBLICATION_APPROVED", actor="owner",
                               explicit_approval=True)])
        self.assertTrue(report["publication_approved_in_supplied_events"])
        self.assertFalse(report["publication_performed"])

    def test_invalid_skip_rejected(self):
        with self.assertRaises(ValueError):
            project_episode(episode_id="colors_ar_01",
                            events=[self.event("PRIVATE_UPLOADED")])

    def test_wrong_episode_rejected(self):
        with self.assertRaises(ValueError):
            project_episode(episode_id="colors_ar_01",
                            events=[dict(episode_id="other", state="SCRIPT_READY")])

    def test_revision_can_return_to_production(self):
        states = ["SCRIPT_READY", "PRODUCTION_PENDING", "RENDER_READY",
                  "PRIVATE_UPLOAD_PENDING", "PRIVATE_UPLOADED",
                  "OWNER_REVIEW_PENDING", "REVISION_REQUIRED",
                  "PRODUCTION_PENDING"]
        report = project_episode(episode_id="colors_ar_01",
                                 events=[self.event(s) for s in states])
        self.assertEqual(report["state"], "PRODUCTION_PENDING")


if __name__ == "__main__":
    unittest.main()
