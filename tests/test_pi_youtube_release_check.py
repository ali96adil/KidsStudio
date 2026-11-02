import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_youtube_release_check import load_credentials, run_check


class PiYouTubePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.credentials = {
            "client_id": "client",
            "client_secret": "secret",
            "refresh_token": "refresh",
            "channel_id": "expected",
        }
        self.path = self.root / "oauth.json"
        self.path.write_text(json.dumps(self.credentials))
        self.path.chmod(0o600)

    def tearDown(self):
        self.tmp.cleanup()

    def test_private_file_loads(self):
        self.assertEqual(load_credentials(self.path), self.credentials)

    def test_world_readable_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            load_credentials(self.path)

    def test_symlink_rejected(self):
        link = self.root / "link.json"
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            load_credentials(link)

    def test_unknown_fields_rejected(self):
        self.path.write_text(json.dumps({**self.credentials, "debug": True}))
        with self.assertRaises(ValueError):
            load_credentials(self.path)

    def test_run_check_is_read_only(self):
        with patch("kidsstudio.pi_youtube_release_check.refresh_access_token", return_value="token") as refresh:
            with patch("kidsstudio.pi_youtube_release_check.inspect_release", return_value={
                "ready_for_manual_release": False,
                "youtube_request_sent": False,
            }) as inspect:
                result = run_check(self.root / "review.db", self.root / "release.db",
                                   self.credentials, "red-ar", "Abc123_defG")
        self.assertFalse(result["youtube_request_sent"])
        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(inspect.call_args.args[-2:], ("expected", "token"))


if __name__ == "__main__":
    unittest.main()
