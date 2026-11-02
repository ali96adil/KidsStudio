import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_media_inbox import build_manifest
from kidsstudio.pi_staging_handoff import prepare_private_upload
from kidsstudio.pi_upload_queue import PiUploadQueue


class SessionIntentRecoveryTests(unittest.TestCase):
    def test_ambiguous_remote_failure_blocks_second_session_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"offline render")
            manifest = build_manifest(source, "red-ar")
            staging = root / "staging"
            staging.mkdir()
            staged = staging / manifest["filename"]
            staged.write_bytes(source.read_bytes())
            metadata = staging / (staged.stem + ".json")
            metadata.write_text(json.dumps(manifest))
            sessions = root / "sessions"
            sessions.mkdir(mode=0o700)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()

            def handoff():
                return prepare_private_upload(
                    staged_video=staged, manifest_path=metadata,
                    inbox_dir=root / "inbox", session_dir=sessions,
                    queue=queue, access_token="offline",
                    expected_channel_id="channel", title="Learn Red",
                )

            with patch("kidsstudio.pi_staging_handoff.start_session",
                       side_effect=OSError("ambiguous network timeout")) as start:
                with self.assertRaises(OSError):
                    handoff()
                self.assertEqual(start.call_count, 1)
            markers = list((sessions / ".session-intents").glob("*.intent"))
            self.assertEqual(len(markers), 1)
            self.assertEqual(markers[0].stat().st_mode & 0o077, 0)
            self.assertEqual(json.loads(markers[0].read_text())["episode_id"], "red-ar")
            with patch("kidsstudio.pi_staging_handoff.start_session") as retry:
                with self.assertRaises(ValueError):
                    handoff()
                retry.assert_not_called()
            self.assertEqual(list(sessions.glob("*.json")), [])
            self.assertIsNone(queue.claim())


if __name__ == "__main__":
    unittest.main()
