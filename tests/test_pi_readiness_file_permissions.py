import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_live_readiness import inspect_live_readiness
from kidsstudio.pi_upload_queue import PiUploadQueue


class ReadinessFilePermissionsTests(unittest.TestCase):
    def test_open_session_file_permissions_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir(mode=0o700)
            sessions.chmod(0o700)
            PiUploadQueue(root / "queue.sqlite").initialize()
            session = sessions / "red-ar.json"
            session.write_text("private-session-url")
            session.chmod(0o600)
            with patch("kidsstudio.pi_live_readiness.inspect_pi_pipeline",
                       return_value={"checks": {"configured": True}}):
                def check():
                    return inspect_live_readiness(
                        state_dir=root, credentials=root / "creds",
                        titles_file=root / "titles",
                    )
                self.assertTrue(check()["checks"]["private_session_files"])
                session.chmod(0o644)
                report = check()
                self.assertFalse(report["checks"]["private_session_files"])
                self.assertNotIn("private-session-url", str(report))
                session.chmod(0o600)
                self.assertTrue(check()["checks"]["private_session_files"])

    def test_open_intent_file_permissions_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sessions" / ".session-intents"
            folder.mkdir(parents=True)
            (root / "sessions").chmod(0o700)
            folder.chmod(0o700)
            PiUploadQueue(root / "queue.sqlite").initialize()
            intent = folder / "legacy.intent"
            intent.write_text("private-intent")
            intent.chmod(0o644)
            with patch("kidsstudio.pi_live_readiness.inspect_pi_pipeline",
                       return_value={"checks": {"configured": True}}):
                report = inspect_live_readiness(
                    state_dir=root, credentials=root / "creds",
                    titles_file=root / "titles",
                )
            self.assertFalse(report["checks"]["private_session_files"])
            self.assertNotIn("private-intent", str(report))


if __name__ == "__main__":
    unittest.main()
