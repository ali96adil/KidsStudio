import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_session_intent_audit import audit_session_intents
from kidsstudio.pi_upload_dashboard import render_upload_dashboard, upload_snapshot
from kidsstudio.pi_upload_queue import PiUploadQueue


class QueuedIntentReconciliationTests(unittest.TestCase):
    def test_queued_episode_has_no_ambiguous_intent_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            folder = sessions / ".session-intents"
            folder.mkdir(parents=True)
            episode, channel = "red-ar", "channel"
            marker = folder / (hashlib.sha256((episode + "\0" + channel).encode()).hexdigest() + ".intent")
            marker.write_text(json.dumps({
                "version": 1, "episode_id": episode, "channel_id": channel,
                "media_sha256": "a" * 64,
            }))
            marker.chmod(0o600)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            queue.enqueue(episode, sessions / "existing.json", channel)
            report = audit_session_intents(sessions, queue.path)
            self.assertEqual(report["pending_reconciliation"], 0)
            self.assertEqual(report["invalid_intents"], 0)
            snapshot = upload_snapshot(queue, sessions)
            self.assertEqual(snapshot["session_intents"]["pending_reconciliation"], 0)
            self.assertIn("Session intents to review", render_upload_dashboard(snapshot))

    def test_unqueued_episode_still_requires_manual_reconciliation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / ".session-intents"
            folder.mkdir()
            episode, channel = "red-ar", "channel"
            marker = folder / (hashlib.sha256((episode + "\0" + channel).encode()).hexdigest() + ".intent")
            marker.write_text(json.dumps({
                "version": 1, "episode_id": episode, "channel_id": channel,
                "media_sha256": "a" * 64,
            }))
            marker.chmod(0o600)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            report = audit_session_intents(root, queue.path)
            self.assertEqual(report["pending_reconciliation"], 1)
            self.assertFalse(report["items"][0]["automatic_retry_allowed"])


if __name__ == "__main__":
    unittest.main()
