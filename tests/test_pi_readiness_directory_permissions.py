import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_live_readiness import inspect_live_readiness
from kidsstudio.pi_upload_queue import PiUploadQueue


class ReadinessDirectoryPermissionTests(unittest.TestCase):
    def test_private_directory_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir(mode=0o700)
            sessions.chmod(0o700)
            PiUploadQueue(root / "queue.sqlite").initialize()
            with patch("kidsstudio.pi_live_readiness.inspect_pi_pipeline",
                       return_value={"checks": {"configured": True}}):
                def check():
                    return inspect_live_readiness(
                        state_dir=root, credentials=root / "credentials",
                        titles_file=root / "titles",
                    )["checks"]["private_session_directories"]
                self.assertTrue(check())
                sessions.chmod(0o755)
                self.assertFalse(check())
                sessions.chmod(0o700)
                intents = sessions / ".session-intents"
                intents.mkdir()
                intents.chmod(0o755)
                self.assertFalse(check())
                intents.chmod(0o700)
                self.assertTrue(check())


if __name__ == "__main__":
    unittest.main()
