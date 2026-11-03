import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_staging_watcher import scan_once
from kidsstudio.pi_upload_queue import PiUploadQueue


class WatcherAmbiguousIntentTests(unittest.TestCase):
    def test_ambiguous_intent_blocks_token_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            staging.mkdir()
            sessions = root / "sessions"
            folder = sessions / ".session-intents"
            folder.mkdir(parents=True)
            episode, channel = "red-ar", "channel"
            digest = hashlib.sha256(b"video").hexdigest()
            name = episode + "-" + digest[:16]
            (staging / (name + ".mp4")).write_bytes(b"video")
            (staging / (name + ".json")).write_text(json.dumps({
                "version": 1, "episode_id": episode,
                "filename": name + ".mp4", "sha256": digest, "size": 5,
            }))
            marker_name = hashlib.sha256((episode + chr(0) + channel).encode()).hexdigest() + ".intent"
            (folder / marker_name).write_text("unresolved")
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            calls = []
            result = scan_once(
                staging_dir=staging, inbox_dir=root / "inbox",
                session_dir=sessions, queue=queue,
                token_provider=lambda: calls.append("token") or "secret",
                expected_channel_id=channel,
                title_for_episode=lambda _: "Colors",
            )
            self.assertEqual(result, [])
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
