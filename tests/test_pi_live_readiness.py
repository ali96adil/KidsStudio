import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_live_readiness import inspect_live_readiness


class LiveReadinessTests(unittest.TestCase):
    def test_missing_queue_fails_closed_without_creating_database(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            with patch("kidsstudio.pi_live_readiness.inspect_pi_pipeline",
                       return_value={"checks": {"configuration": True}}):
                result = inspect_live_readiness(
                    state_dir=state, credentials=state / "missing.json",
                    titles_file=state / "titles.json",
                )
            self.assertFalse(result["ready_for_hardware_test"])
            self.assertFalse(result["checks"]["upload_queue_readable"])
            self.assertFalse((state / "queue.sqlite").exists())
            self.assertFalse(result["youtube_upload_tested"])
            self.assertFalse(result["public_release_enabled"])

    def test_bad_config_never_reports_ready(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            result = inspect_live_readiness(
                state_dir=state, credentials=state / "missing.json",
                titles_file=state / "missing-titles.json",
            )
            self.assertFalse(result["ready_for_hardware_test"])
            self.assertFalse(result["checks"]["credentials_private_and_valid"])


if __name__ == "__main__":
    unittest.main()
