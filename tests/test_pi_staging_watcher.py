import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_media_inbox import build_manifest
from kidsstudio.pi_staging_watcher import scan_once
from kidsstudio.pi_upload_queue import PiUploadQueue


class StagingWatcherTests(unittest.TestCase):
    def test_complete_manifest_queues_once(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            staging = base / "staging"
            staging.mkdir()
            video = staging / "red.mp4"
            video.write_bytes(b"rendered video")
            manifest = build_manifest(video, "red-ar")
            target = staging / ("red-ar-" + manifest["sha256"][:16] + ".mp4")
            video.rename(target)
            manifest["filename"] = target.name
            (staging / (target.stem + ".json")).write_text(json.dumps(manifest))
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            params = dict(
                staging_dir=staging, inbox_dir=base / "inbox",
                session_dir=base / "sessions", queue=queue,
                token_provider=lambda: "token", expected_channel_id="channel",
                title_for_episode=lambda episode: "Learn Red",
            )
            with patch("kidsstudio.pi_staging_handoff.start_session",
                       return_value="https://www.googleapis.com/upload/session") as start:
                self.assertEqual(len(scan_once(**params)), 1)
                self.assertEqual(scan_once(**params), [])
                self.assertEqual(start.call_count, 1)
            self.assertEqual(queue.claim()["episode_id"], "red-ar")

    def test_incomplete_file_is_skipped_without_token(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            staging = base / "staging"
            staging.mkdir()
            video = staging / "red.mp4"
            video.write_bytes(b"original")
            manifest = build_manifest(video, "red-ar")
            target = staging / ("red-ar-" + manifest["sha256"][:16] + ".mp4")
            video.rename(target)
            manifest["filename"] = target.name
            (staging / (target.stem + ".json")).write_text(json.dumps(manifest))
            target.write_bytes(b"partial")
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            called = []
            result = scan_once(
                staging_dir=staging, inbox_dir=base / "inbox",
                session_dir=base / "sessions", queue=queue,
                token_provider=lambda: called.append("token"),
                expected_channel_id="channel",
                title_for_episode=lambda episode: "Learn Red",
            )
            self.assertEqual(result, [])
            self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
