import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kidsstudio.pi_media_inbox import build_manifest
from kidsstudio.pi_staging_handoff import prepare_private_upload
from kidsstudio.pi_staging_watcher import scan_once
from kidsstudio.pi_upload_queue import PiUploadQueue


class EpisodeHandoffGuardTests(unittest.TestCase):
    def test_duplicate_episode_different_media_never_starts_youtube_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            staging.mkdir()
            inbox = root / "inbox"
            sessions = root / "sessions"
            sessions.mkdir(mode=0o700)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red-ar", sessions / "old-session.json", "channel")
            source = root / "render.mp4"
            source.write_bytes(b"new edited render")
            manifest = build_manifest(source, "red-ar")
            staged = staging / manifest["filename"]
            staged.write_bytes(source.read_bytes())
            manifest_file = staging / (staged.stem + ".json")
            manifest_file.write_text(json.dumps(manifest))
            token = Mock(side_effect=AssertionError("OAuth must not be called"))
            with patch("kidsstudio.pi_staging_handoff.start_session") as youtube:
                result = scan_once(
                    staging_dir=staging, inbox_dir=inbox, session_dir=sessions,
                    queue=queue, token_provider=token, expected_channel_id="channel",
                    title_for_episode=lambda _: "Learn Red",
                )
                self.assertEqual(result, [])
                token.assert_not_called()
                with self.assertRaises(ValueError):
                    prepare_private_upload(
                        staged_video=staged, manifest_path=manifest_file,
                        inbox_dir=inbox, session_dir=sessions, queue=queue,
                        access_token="offline", expected_channel_id="channel",
                        title="Learn Red",
                    )
                youtube.assert_not_called()


if __name__ == "__main__":
    unittest.main()
