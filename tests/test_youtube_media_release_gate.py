import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_media_approval import MediaApprovalStore, sha256_video
from kidsstudio.owner_release_gate import OwnerReleaseGate
from kidsstudio.owner_review_store import OwnerReviewStore
from kidsstudio.youtube_media_release_gate import media_bound_release_plan


class MediaBoundReleaseTests(unittest.TestCase):
    def test_changed_render_requires_new_approval(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            reviews = OwnerReviewStore(folder / "reviews.db")
            releases = OwnerReleaseGate(folder / "releases.db")
            media = MediaApprovalStore(folder / "media.db")
            reviews.initialize()
            releases.initialize()
            media.initialize()
            video = folder / "red.mp4"
            video.write_bytes(b"render v1")
            reviews.record(episode_id="red", state="approved", note="ok")
            releases.record("red", "release_authorized", "owner")
            def plan():
                return media_bound_release_plan(reviews, releases, media, "red", "Abc123_defG", "private", video)
            self.assertFalse(plan()["ready_for_manual_release"])
            media.record("red", sha256_video(video), "approved")
            self.assertTrue(plan()["ready_for_manual_release"])
            video.write_bytes(b"render v2")
            self.assertFalse(plan()["ready_for_manual_release"])
            self.assertIsNone(plan()["requested_privacy"])


if __name__ == "__main__":
    unittest.main()
