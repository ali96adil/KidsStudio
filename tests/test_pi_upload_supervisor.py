import unittest
from unittest.mock import patch
from urllib.error import URLError

from kidsstudio.pi_upload_supervisor import supervise_resume
from kidsstudio.youtube_resumable_upload import UploadError


class UploadSupervisorTests(unittest.TestCase):
    def test_refreshes_on_each_retry(self):
        failure = UploadError("offline")
        failure.__cause__ = URLError("offline")
        tokens = iter(("token-1", "token-2"))
        delays = []
        with patch("kidsstudio.pi_upload_supervisor.load_session", return_value={}):
            with patch("kidsstudio.pi_upload_supervisor.resume_private_upload",
                       side_effect=[failure, {"recorded_private_upload": True}]) as upload:
                result = supervise_resume(
                    object(), episode_id="red", session_path="session.json",
                    expected_channel_id="channel", token_provider=lambda: next(tokens),
                    sleep=delays.append,
                )
        self.assertTrue(result["recorded_private_upload"])
        self.assertEqual(upload.call_args_list[0].kwargs["access_token"], "token-1")
        self.assertEqual(upload.call_args_list[1].kwargs["access_token"], "token-2")
        self.assertEqual(delays, [2.0])

    def test_corrupt_session_does_not_fetch_token(self):
        called = []
        with patch("kidsstudio.pi_upload_supervisor.load_session", side_effect=ValueError("changed")):
            with self.assertRaises(ValueError):
                supervise_resume(
                    object(), episode_id="red", session_path="session.json",
                    expected_channel_id="channel",
                    token_provider=lambda: called.append(True),
                )
        self.assertEqual(called, [])

    def test_permanent_failure_does_not_retry(self):
        failure = UploadError("rejected")
        with patch("kidsstudio.pi_upload_supervisor.load_session", return_value={}):
            with patch("kidsstudio.pi_upload_supervisor.resume_private_upload",
                       side_effect=failure) as upload:
                with self.assertRaises(UploadError):
                    supervise_resume(
                        object(), episode_id="red", session_path="session.json",
                        expected_channel_id="channel", token_provider=lambda: "token",
                        sleep=lambda _: None,
                    )
                self.assertEqual(upload.call_count, 1)


if __name__ == "__main__":
    unittest.main()
