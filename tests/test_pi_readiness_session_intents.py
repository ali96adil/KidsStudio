import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_live_readiness import inspect_live_readiness
from kidsstudio.pi_upload_queue import PiUploadQueue


class ReadinessIntentTests(unittest.TestCase):
    def test_unresolved_intent_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            folder = sessions / ".session-intents"
            folder.mkdir(parents=True)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            episode, channel = "red-ar", "channel"
            name = hashlib.sha256((episode + chr(0) + channel).encode()).hexdigest() + ".intent"
            marker = folder / name
            marker.write_text(json.dumps({
                "version": 1, "episode_id": episode, "channel_id": channel,
                "media_sha256": "a" * 64,
            }))
            marker.chmod(0o600)
            with patch("kidsstudio.pi_live_readiness.inspect_pi_pipeline",
                       return_value={"checks": {"configured": True}}):
                report = inspect_live_readiness(
                    state_dir=root, credentials=root / "credentials",
                    titles_file=root / "titles",
                )
            self.assertFalse(report["ready_for_hardware_test"])
            self.assertFalse(report["checks"]["no_ambiguous_session_intents"])
            self.assertFalse(report["youtube_upload_tested"])

    def test_invalid_intent_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "sessions" / ".session-intents"
            folder.mkdir(parents=True)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            marker = folder / "bad.intent"
            marker.write_text("invalid")
            marker.chmod(0o600)
            with patch("kidsstudio.pi_live_readiness.inspect_pi_pipeline",
                       return_value={"checks": {"configured": True}}):
                report = inspect_live_readiness(
                    state_dir=root, credentials=root / "credentials",
                    titles_file=root / "titles",
                )
            self.assertFalse(report["checks"]["no_ambiguous_session_intents"])


if __name__ == "__main__":
    unittest.main()
