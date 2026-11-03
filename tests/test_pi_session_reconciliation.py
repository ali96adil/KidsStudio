import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_session_reconciliation import reconciliation_report
from kidsstudio.pi_upload_queue import PiUploadQueue


class SessionReconciliationTests(unittest.TestCase):
    def test_pending_intent_and_missing_job_session_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            intents = sessions / ".session-intents"
            intents.mkdir(parents=True)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            queue.enqueue("blue-ar", sessions / "missing.json", "channel")
            episode, channel = "red-ar", "channel"
            name = hashlib.sha256((episode + chr(0) + channel).encode()).hexdigest() + ".intent"
            marker = intents / name
            marker.write_text(json.dumps({
                "version": 1, "episode_id": episode, "channel_id": channel,
                "media_sha256": "a" * 64,
                "state": "manual_reconcile_if_session_missing",
                "access_token": "secret-do-not-print",
            }))
            marker.chmod(0o600)
            report = reconciliation_report(root)
            self.assertTrue(report["read_only"])
            self.assertFalse(report["youtube_checked"])
            self.assertEqual(report["pending_reconciliation"], 1)
            self.assertEqual(len(report["episodes"]), 2)
            entries = {e["episode_id"]: e for e in report["episodes"]}
            self.assertEqual(entries["red-ar"]["queue_state"], "not_queued")
            self.assertEqual(entries["blue-ar"]["queue_state"], "pending")
            self.assertFalse(entries["blue-ar"]["session_saved"])
            self.assertTrue(all(not e["automatic_new_upload_allowed"] for e in report["episodes"]))
            self.assertNotIn("secret-do-not-print", str(report))
            self.assertNotIn(str(root), str(report))


if __name__ == "__main__":
    unittest.main()
