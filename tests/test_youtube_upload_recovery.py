import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from kidsstudio.youtube_upload_session import load_session, save_session
from kidsstudio.youtube_upload_recovery import query_upload_progress, resume_saved_upload


class RecoveryTests(unittest.TestCase):
    def test_saved_session_validates_file(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            video = folder / "video.mp4"
            video.write_bytes(b"first")
            session = folder / "session.json"
            save_session(session, session_url="https://www.googleapis.com/upload/session", video_path=video)
            self.assertEqual(load_session(session)["offset"], 0)
            self.assertEqual(session.stat().st_mode & 0o077, 0)
            video.write_bytes(b"other")
            with self.assertRaises(ValueError):
                load_session(session)

    def test_server_offset_from_308(self):
        error = HTTPError("https://www.googleapis.com/upload/session", 308, "resume",
                          {"Range": "bytes=0-3"}, None)
        with patch("kidsstudio.youtube_upload_recovery.urlopen", side_effect=error):
            offset, receipt = query_upload_progress("https://www.googleapis.com/upload/session", "token", 10)
        self.assertEqual(offset, 4)
        self.assertIsNone(receipt)

    def test_resume_uses_server_offset_not_saved_offset(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            video = folder / "video.mp4"
            video.write_bytes(b"abcdefghij")
            session = folder / "session.json"
            save_session(session, session_url="https://www.googleapis.com/upload/session",
                         video_path=video, offset=2)
            with patch("kidsstudio.youtube_upload_recovery.query_upload_progress",
                       return_value=(6, None)):
                with patch("kidsstudio.youtube_upload_recovery.upload_video",
                           return_value={"status": {"privacyStatus": "private"}}) as upload:
                    resume_saved_upload(session, "token")
                    self.assertEqual(upload.call_args.kwargs["offset"], 6)


if __name__ == "__main__":
    unittest.main()
