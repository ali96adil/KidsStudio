import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_pipeline_service import pipeline_tick, read_titles


class PipelineServiceTests(unittest.TestCase):
    def test_combines_watcher_and_worker(self):
        with patch("kidsstudio.pi_pipeline_service.scan_once", return_value=[{"queued": True}]) as watcher:
            with patch("kidsstudio.pi_pipeline_service.process_one",
                       return_value={"job_id": 1}) as worker:
                result = pipeline_tick(
                    queue=object(), bindings=object(), staging_dir="/tmp/staging",
                    inbox_dir="/tmp/inbox", session_dir="/tmp/sessions",
                    token_provider=lambda: "token", channel_id="channel",
                    titles={"red-ar": "Learn Red"},
                )
        self.assertEqual(result, {"queued": 1, "processed": True, "watcher_error": False})
        self.assertEqual(watcher.call_args.kwargs["title_for_episode"]("red-ar"), "Learn Red")
        self.assertEqual(watcher.call_args.kwargs["title_for_episode"]("unknown"), "")
        worker.assert_called_once()

    def test_trusted_title_metadata(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "titles.json"
            source.write_text(json.dumps({"red-ar": "Learn Red"}))
            self.assertEqual(read_titles(source)["red-ar"], "Learn Red")
            source.write_text(json.dumps({"red-ar": ""}))
            with self.assertRaises(ValueError):
                read_titles(source)


if __name__ == "__main__":
    unittest.main()
