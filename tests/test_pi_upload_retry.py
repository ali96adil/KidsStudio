import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from kidsstudio.pi_upload_retry import is_retryable_upload_error, resume_with_retries
from kidsstudio.youtube_resumable_upload import UploadError


class RetryTests(unittest.TestCase):
    def test_retry_classification(self):
        for code in (408, 429, 500, 503):
            exc = UploadError("failed")
            exc.__cause__ = HTTPError("https://example.invalid", code, "error", {}, None)
            self.assertTrue(is_retryable_upload_error(exc))
        exc = UploadError("failed")
        exc.__cause__ = HTTPError("https://example.invalid", 403, "denied", {}, None)
        self.assertFalse(is_retryable_upload_error(exc))
        exc = UploadError("offline")
        exc.__cause__ = URLError("offline")
        self.assertTrue(is_retryable_upload_error(exc))

    def test_transient_failure_retries(self):
        offline = UploadError("offline")
        offline.__cause__ = URLError("offline")
        sleeps = []
        with patch("kidsstudio.pi_upload_retry.load_session", return_value={}):
            with patch("kidsstudio.pi_upload_retry.resume_private_upload",
                       side_effect=[offline, {"recorded_private_upload": True}]) as runner:
                result = resume_with_retries(
                    object(), episode_id="red", session_path="session.json",
                    expected_channel_id="channel", access_token="token",
                    sleep=sleeps.append,
                )
        self.assertTrue(result["recorded_private_upload"])
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(sleeps, [2.0])

    def test_permanent_failure_no_retry(self):
        denied = UploadError("denied")
        denied.__cause__ = HTTPError("https://example.invalid", 403, "denied", {}, None)
        with patch("kidsstudio.pi_upload_retry.load_session", return_value={}):
            with patch("kidsstudio.pi_upload_retry.resume_private_upload", side_effect=denied) as runner:
                with self.assertRaises(UploadError):
                    resume_with_retries(
                        object(), episode_id="red", session_path="session.json",
                        expected_channel_id="channel", access_token="token",
                        sleep=lambda _: None,
                    )
                self.assertEqual(runner.call_count, 1)

    def test_bad_attempts(self):
        with self.assertRaises(ValueError):
            resume_with_retries(object(), episode_id="red", session_path="s",
                                expected_channel_id="c", access_token="t", attempts=0)


if __name__ == "__main__":
    unittest.main()
