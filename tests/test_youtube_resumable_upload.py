import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from kidsstudio.youtube_resumable_upload import (
    UploadError, parse_range_offset, start_session, upload_chunk, upload_video,
)


class FakeResponse:
    status = 200
    def __init__(self, data=b"{}", headers=None):
        self.data = data
        self.headers = headers or {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        return self.data[:size]


class ResumableTests(unittest.TestCase):
    def test_start_session_is_private(self):
        with patch("kidsstudio.youtube_resumable_upload.urlopen",
                   return_value=FakeResponse(headers={"Location": "https://www.googleapis.com/upload/session"})) as opener:
            url = start_session("token", 1234, "Colors")
            self.assertIn("session", url)
            body = json.loads(opener.call_args.args[0].data)
            self.assertEqual(body["status"]["privacyStatus"], "private")
            self.assertTrue(body["status"]["selfDeclaredMadeForKids"])

    def test_parse_range(self):
        self.assertEqual(parse_range_offset("bytes=0-511", 1024), 512)
        self.assertEqual(parse_range_offset(None, 1024), 0)
        with self.assertRaises(UploadError):
            parse_range_offset("bytes=100-511", 1024)

    def test_partial_308(self):
        error = HTTPError("https://www.googleapis.com/", 308, "resume", {"Range": "bytes=0-3"}, None)
        with patch("kidsstudio.youtube_resumable_upload.urlopen", side_effect=error):
            offset, result = upload_chunk("https://www.googleapis.com/session", "token", b"abcd", 0, 8)
        self.assertEqual(offset, 4)
        self.assertIsNone(result)

    def test_upload_video_completion(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "clip.mp4"
            path.write_bytes(b"abcdef")
            receipt = {"id": "Abc123_defG", "status": {"privacyStatus": "private"}}
            with patch("kidsstudio.youtube_resumable_upload.upload_chunk", return_value=(6, receipt)) as chunk:
                self.assertEqual(upload_video("https://www.googleapis.com/session", "token", path), receipt)
                self.assertEqual(chunk.call_args.args[2], b"abcdef")

    def test_public_response_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "clip.mp4"
            path.write_bytes(b"x")
            with patch("kidsstudio.youtube_resumable_upload.upload_chunk",
                       return_value=(1, {"status": {"privacyStatus": "public"}})):
                with self.assertRaises(UploadError):
                    upload_video("https://www.googleapis.com/session", "token", path)


if __name__ == "__main__":
    unittest.main()
