import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_private_upload_runner import start_private_upload, resume_private_upload
from kidsstudio.youtube_upload_binding import UploadBindingStore
from kidsstudio.youtube_resumable_upload import UploadError
from kidsstudio.youtube_upload_session import save_session
from kidsstudio.owner_media_approval import sha256_video


class PrivateRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root / "clip.mp4"
        self.video.write_bytes(b"video bytes")
        self.bindings = UploadBindingStore(self.root / "uploads.db")
        self.bindings.initialize()
        self.session = self.root / "session.json"
        self.upload_response = {"id": "Abc123_defG", "status": {"privacyStatus": "private"}}

    def tearDown(self):
        self.temp.cleanup()

    def test_start_verifies_and_records(self):
        with patch("kidsstudio.pi_private_upload_runner.start_session", return_value="https://www.googleapis.com/upload/session"):
            with patch("kidsstudio.pi_private_upload_runner.upload_video", return_value=self.upload_response):
                with patch("kidsstudio.pi_private_upload_runner.inspect_video", return_value={
                    "video_id": "Abc123_defG", "channel_id": "channel", "privacy": "private"
                }):
                    result = start_private_upload(
                        self.bindings, episode_id="red", video_path=self.video,
                        title="Colors", description="", expected_channel_id="channel",
                        access_token="token", session_path=self.session,
                    )
        self.assertTrue(result["recorded_private_upload"])
        self.assertTrue(self.bindings.matches_latest("red", sha256_video(self.video), "Abc123_defG", "channel"))
        self.assertEqual(self.session.stat().st_mode & 0o077, 0)

    def test_wrong_channel_never_records(self):
        with patch("kidsstudio.pi_private_upload_runner.start_session", return_value="https://www.googleapis.com/upload/session"):
            with patch("kidsstudio.pi_private_upload_runner.upload_video", return_value=self.upload_response):
                with patch("kidsstudio.pi_private_upload_runner.inspect_video", return_value={
                    "video_id": "Abc123_defG", "channel_id": "other", "privacy": "private"
                }):
                    with self.assertRaises(UploadError):
                        start_private_upload(
                            self.bindings, episode_id="red", video_path=self.video,
                            title="Colors", description="", expected_channel_id="channel",
                            access_token="token", session_path=self.session,
                        )
        self.assertFalse(self.bindings.matches_latest("red", sha256_video(self.video), "Abc123_defG", "channel"))

    def test_resume_uses_saved_video(self):
        save_session(self.session, session_url="https://www.googleapis.com/upload/session", video_path=self.video)
        with patch("kidsstudio.pi_private_upload_runner.resume_saved_upload", return_value=self.upload_response):
            with patch("kidsstudio.pi_private_upload_runner.inspect_video", return_value={
                "video_id": "Abc123_defG", "channel_id": "channel", "privacy": "private"
            }):
                result = resume_private_upload(
                    self.bindings, episode_id="red", session_path=self.session,
                    expected_channel_id="channel", access_token="token",
                )
        self.assertTrue(result["recorded_private_upload"])


if __name__ == "__main__":
    unittest.main()
