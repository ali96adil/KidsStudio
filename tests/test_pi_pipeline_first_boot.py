import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_pipeline_service import run_pipeline


class FirstBootTests(unittest.TestCase):
    def test_first_boot_creates_private_media_folders(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            state = base / "private-upload"
            credentials = base / "youtube.json"
            credentials.write_text(json.dumps({
                "client_id": "test", "client_secret": "test",
                "refresh_token": "test", "channel_id": "channel",
            }))
            credentials.chmod(0o600)
            titles = base / "titles.json"
            titles.write_text(json.dumps({"red-ar": "Learn Red"}))
            with patch("kidsstudio.pi_pipeline_service.pipeline_tick") as tick:
                result = run_pipeline(
                    state_dir=state, credentials=credentials,
                    titles_file=titles, once=True,
                )
            self.assertEqual(result, 0)
            tick.assert_called_once()
            for folder in ("staging", "inbox", "sessions"):
                directory = state / folder
                self.assertTrue(directory.is_dir())
                self.assertEqual(directory.stat().st_mode & 0o777, 0o700)


if __name__ == "__main__":
    unittest.main()
