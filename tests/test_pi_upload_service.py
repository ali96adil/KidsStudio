import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_upload_service import run_service


class UploadServiceTests(unittest.TestCase):
    def test_once_starts_queue_and_processes_one(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "private"
            with patch("kidsstudio.pi_upload_service.process_one", return_value=None) as process:
                result = run_service(state_dir=state, credential_path="/tmp/fake.json", once=True)
            self.assertEqual(result, 0)
            self.assertEqual(process.call_count, 1)
            self.assertEqual(state.stat().st_mode & 0o077, 0)
            self.assertTrue((state / "queue.sqlite").exists())
            self.assertTrue((state / "bindings.sqlite").exists())

    def test_rejects_world_readable_state(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root) / "private"
            state.mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                run_service(state_dir=state, credential_path="/tmp/fake.json", once=True)


if __name__ == "__main__":
    unittest.main()
