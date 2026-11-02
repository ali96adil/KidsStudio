import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_pipeline_service import run_pipeline


class WatcherExitTests(unittest.TestCase):
    def test_once_reports_watcher_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            creds = root / "creds.json"
            creds.write_text(json.dumps({
                "client_id": "offline", "client_secret": "offline",
                "refresh_token": "offline", "channel_id": "test-channel",
            }))
            creds.chmod(0o600)
            titles = root / "titles.json"
            titles.write_text('{"red-ar":"Red"}')
            with patch("kidsstudio.pi_pipeline_service.pipeline_tick",
                       return_value={"queued": 0, "processed": True, "watcher_error": True}):
                code = run_pipeline(
                    state_dir=root / "state", credentials=creds,
                    titles_file=titles, once=True,
                )
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
