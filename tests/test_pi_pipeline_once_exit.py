import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_pipeline_service import run_pipeline


class PiPipelineOnceExitTests(unittest.TestCase):
    def test_once_returns_failure_on_tick_error(self):
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
                       side_effect=RuntimeError("private OAuth secret")):
                with patch("kidsstudio.pi_pipeline_service.sys.stderr") as stderr:
                    result = run_pipeline(
                        state_dir=root / "state", credentials=creds,
                        titles_file=titles, once=True,
                    )
            self.assertEqual(result, 2)
            self.assertNotIn("private OAuth secret", str(stderr.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
