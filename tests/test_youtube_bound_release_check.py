import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.owner_media_approval import MediaApprovalStore, sha256_video
from kidsstudio.owner_release_gate import OwnerReleaseGate
from kidsstudio.owner_review_store import OwnerReviewStore
from kidsstudio.youtube_upload_binding import UploadBindingStore
from kidsstudio.youtube_bound_release_check import inspect_bound_release


class BoundReleaseTests(unittest.TestCase):
    def test_exact_upload_binding_is_required(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            reviews = OwnerReviewStore(folder / "reviews.db")
            releases = OwnerReleaseGate(folder / "release.db")
            media = MediaApprovalStore(folder / "media.db")
            uploads = UploadBindingStore(folder / "uploads.db")
            for store in (reviews, releases, media, uploads):
                store.initialize()
            video = folder / "red.mp4"
            video.write_bytes(b"approved render")
            digest = sha256_video(video)
            reviews.record(episode_id="red", state="approved", note="ok")
            releases.record("red", "release_authorized", "owner")
            media.record("red", digest, "approved")
            def check():
                return inspect_bound_release(
                    reviews, releases, media, uploads, "red",
                    "Abc123_defG", "channel", "token", video
                )
            with patch("kidsstudio.youtube_release_inspection.inspect_video",
                       return_value={"channel_id": "channel", "privacy": "private"}):
                self.assertFalse(check()["ready_for_manual_release"])
                uploads.record("red", digest, "Abc123_defG", "channel")
                self.assertTrue(check()["ready_for_manual_release"])
                video.write_bytes(b"re-rendered")
                self.assertFalse(check()["ready_for_manual_release"])


if __name__ == "__main__":
    unittest.main()
