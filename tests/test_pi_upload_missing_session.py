import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_session_audit import audit_sessions


class MissingSessionAuditTests(unittest.TestCase):
    def test_missing_queued_session_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            sessions = base / "sessions"
            sessions.mkdir()
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            missing = sessions / "sensitive-episode-session.json"
            queue.enqueue("episode-red", missing, "channel")
            report = audit_sessions(queue, sessions)
            self.assertFalse(report["healthy"])
            self.assertEqual(report["counts"]["missing"], 1)
            self.assertIn("missing_queued_session", report["problems"])
            self.assertNotIn(str(missing), str(report))

    def test_missing_sessions_not_counted_for_empty_queue(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            sessions = base / "sessions"
            sessions.mkdir()
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            report = audit_sessions(queue, sessions)
            self.assertTrue(report["healthy"])
            self.assertEqual(report["counts"]["missing"], 0)


if __name__ == "__main__":
    unittest.main()
