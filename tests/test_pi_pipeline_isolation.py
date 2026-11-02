import unittest
from unittest.mock import patch

from kidsstudio.pi_pipeline_service import pipeline_tick


class PipelineIsolationTests(unittest.TestCase):
    def test_staging_error_does_not_block_existing_queue(self):
        with patch("kidsstudio.pi_pipeline_service.scan_once",
                   side_effect=ValueError("invalid staging")) as watcher, patch(
                       "kidsstudio.pi_pipeline_service.process_one",
                       return_value={"id": 3}) as worker:
            result = pipeline_tick(
                queue=object(), bindings=object(),
                staging_dir="staging", inbox_dir="inbox",
                session_dir="sessions", token_provider=object(),
                channel_id="channel", titles={},
            )
        self.assertTrue(result["watcher_error"])
        self.assertTrue(result["processed"])
        self.assertEqual(result["queued"], 0)
        watcher.assert_called_once()
        worker.assert_called_once()

    def test_clean_tick_reports_no_watcher_error(self):
        with patch("kidsstudio.pi_pipeline_service.scan_once",
                   return_value=[{"job_id": 1}]), patch(
                       "kidsstudio.pi_pipeline_service.process_one",
                       return_value=None):
            result = pipeline_tick(
                queue=object(), bindings=object(),
                staging_dir="staging", inbox_dir="inbox",
                session_dir="sessions", token_provider=object(),
                channel_id="channel", titles={},
            )
        self.assertEqual(result, {
            "queued": 1, "processed": False, "watcher_error": False,
        })


if __name__ == "__main__":
    unittest.main()
