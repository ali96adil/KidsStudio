import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_pipeline_preflight import inspect_pi_pipeline


class PiPreflightTests(unittest.TestCase):
    def test_missing_configuration_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            result = inspect_pi_pipeline(
                state_dir=Path(root) / "missing",
                credentials=Path(root) / "missing-creds.json",
                titles_file=Path(root) / "missing-titles.json",
            )
            self.assertFalse(result["ready"])
            self.assertFalse(result["network_checked"])
            self.assertFalse(result["youtube_upload_tested"])

    def test_private_configuration_is_ready_for_live_test(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            state = base / "private-upload"
            state.mkdir(mode=0o700)
            for name in ("staging", "inbox", "sessions"):
                (state / name).mkdir(mode=0o700)
            credentials = base / "youtube.json"
            credentials.write_text(json.dumps({
                "client_id": "example", "client_secret": "example",
                "refresh_token": "example", "channel_id": "channel",
            }))
            credentials.chmod(0o600)
            titles = base / "titles.json"
            titles.write_text(json.dumps({"red-ar": "Learn Red"}))
            titles.chmod(0o600)
            result = inspect_pi_pipeline(
                state_dir=state, credentials=credentials, titles_file=titles,
            )
            self.assertTrue(result["ready"])
            self.assertFalse(result["youtube_upload_tested"])
            titles.chmod(0o644)
            self.assertFalse(inspect_pi_pipeline(
                state_dir=state, credentials=credentials, titles_file=titles,
            )["ready"])


if __name__ == "__main__":
    unittest.main()
