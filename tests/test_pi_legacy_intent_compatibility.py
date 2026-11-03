import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_session_intent_names import intent_filenames
from kidsstudio.pi_session_intent_audit import audit_session_intents
from kidsstudio.pi_staging_watcher import scan_once
from kidsstudio.pi_upload_queue import PiUploadQueue


class LegacyIntentCompatibilityTests(unittest.TestCase):
    def test_legacy_marker_is_audited_and_blocks_oauth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            folder = sessions / ".session-intents"
            folder.mkdir(parents=True)
            staging = root / "staging"
            staging.mkdir()
            episode, channel = "red-ar", "channel"
            canonical, legacy = intent_filenames(episode, channel)
            self.assertNotEqual(canonical, legacy)
            digest = hashlib.sha256(b"video").hexdigest()
            name = episode + "-" + digest[:16]
            (staging / (name + ".mp4")).write_bytes(b"video")
            (staging / (name + ".json")).write_text(json.dumps({
                "version": 1, "episode_id": episode, "filename": name + ".mp4",
                "sha256": digest, "size": 5,
            }))
            marker = folder / legacy
            marker.write_text(json.dumps({
                "version": 1, "episode_id": episode, "channel_id": channel,
                "media_sha256": digest, "state": "manual_reconcile_if_session_missing",
            }))
            marker.chmod(0o600)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            report = audit_session_intents(sessions, queue.path)
            self.assertEqual(report["invalid_intents"], 0)
            self.assertEqual(report["pending_reconciliation"], 1)
            calls = []
            results = scan_once(
                staging_dir=staging, inbox_dir=root / "inbox",
                session_dir=sessions, queue=queue,
                token_provider=lambda: calls.append("oauth") or "token",
                expected_channel_id=channel, title_for_episode=lambda _: "Colors",
            )
            self.assertEqual(results, [])
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
