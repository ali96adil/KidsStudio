import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_session_audit import audit_sessions


class InvalidReferencedSessionTests(unittest.TestCase):
    def test_corrupt_existing_session_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            sessions = base / "sessions"
            sessions.mkdir()
            session = sessions / "colors-red-ar-invalid.json"
            session.write_text("not valid JSON")
            session.chmod(0o600)
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            queue.enqueue("colors-red-ar", session, "channel")
            report = audit_sessions(queue, sessions)
            self.assertFalse(report["healthy"])
            self.assertEqual(report["counts"]["corrupt"], 1)
            self.assertEqual(report["counts"]["invalid_referenced"], 1)
            self.assertIn("invalid_referenced_session", report["problems"])
            self.assertNotIn(str(session), str(report))


if __name__ == "__main__":
    unittest.main()
