import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_media_approval import sha256_video
from kidsstudio.youtube_upload_binding import UploadBindingStore
from kidsstudio.pi_private_upload_receipt import record_private_upload


class PrivateReceiptTests(unittest.TestCase):
    def test_private_success_only(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            video = folder / "episode.mp4"
            video.write_bytes(b"final media")
            digest = sha256_video(video)
            store = UploadBindingStore(folder / "uploads.db")
            store.initialize()
            receipt = {
                "privacy": "private",
                "upload_succeeded": True,
                "video_id": "Abc123_defG",
                "channel_id": "my-channel",
                "media_sha256": digest,
            }
            def record(candidate):
                return record_private_upload(
                    store, episode_id="red-ar", local_video=video,
                    receipt=candidate, expected_channel_id="my-channel"
                )
            for changes in (
                {"privacy": "public"},
                {"upload_succeeded": False},
                {"channel_id": "other"},
                {"media_sha256": "0" * 64},
                {"video_id": "invalid"},
            ):
                with self.subTest(changes=changes):
                    with self.assertRaises(ValueError):
                        record({**receipt, **changes})
            self.assertFalse(store.matches_latest("red-ar", digest, "Abc123_defG", "my-channel"))
            result = record(receipt)
            self.assertTrue(result["recorded_private_upload"])
            self.assertFalse(result["youtube_visibility_changed"])
            self.assertTrue(store.matches_latest("red-ar", digest, "Abc123_defG", "my-channel"))


if __name__ == "__main__":
    unittest.main()
