import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_session_intent_audit import audit_session_intents
from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_dashboard import upload_snapshot, render_upload_dashboard


class SessionIntentAuditTests(unittest.TestCase):
    def test_valid_intent_is_visible_without_sensitive_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            sessions = state / "sessions"
            folder = sessions / ".session-intents"
            folder.mkdir(parents=True)
            marker = folder / "test.intent"
            marker.write_text(json.dumps({
                "version": 1, "episode_id": "red-ar", "channel_id": "secret-channel",
                "media_sha256": "a" * 64,
                "state": "manual_reconcile_if_session_missing",
                "session_url": "https://secret.example/session-token",
            }))
            marker.chmod(0o600)
            queue = PiUploadQueue(state / "queue.sqlite")
            queue.initialize()
            report = audit_session_intents(sessions)
            self.assertEqual(report["pending_reconciliation"], 1)
            self.assertFalse(report["items"][0]["automatic_retry_allowed"])
            self.assertNotIn("secret", str(report))
            snapshot = upload_snapshot(queue, sessions)
            html = render_upload_dashboard(snapshot)
            self.assertIn("Session intents to review", html)
            self.assertIn("Attention required", html)
            self.assertNotIn("secret", html)

    def test_invalid_intent_is_counted_without_echoing_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ".session-intents"
            folder.mkdir()
            marker = folder / "bad.intent"
            marker.write_text("private-token")
            marker.chmod(0o600)
            report = audit_session_intents(tmp)
            self.assertEqual(report["invalid_intents"], 1)
            self.assertNotIn("private-token", str(report))


if __name__ == "__main__":
    unittest.main()
