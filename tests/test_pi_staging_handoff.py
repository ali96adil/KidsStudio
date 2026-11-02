import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_media_inbox import build_manifest
from kidsstudio.pi_staging_handoff import prepare_private_upload
from kidsstudio.pi_upload_queue import PiUploadQueue


class StagingHandoffTests(unittest.TestCase):
    def test_handoff_creates_private_session_and_queue_job(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            video = base / "red.mp4"
            video.write_bytes(b"example media")
            manifest = base / "red.json"
            manifest.write_text(json.dumps(build_manifest(video, "red-ar")))
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            with patch("kidsstudio.pi_staging_handoff.start_session",
                       return_value="https://www.googleapis.com/upload/session") as start:
                result = prepare_private_upload(
                    staged_video=video, manifest_path=manifest,
                    inbox_dir=base / "inbox", session_dir=base / "sessions",
                    queue=queue, access_token="token", expected_channel_id="channel",
                    title="Learn Red",
                )
            self.assertTrue(result["queued"])
            self.assertEqual(result["privacy"], "private")
            self.assertEqual(queue.claim()["episode_id"], "red-ar")
            self.assertEqual(start.call_count, 1)
            with self.assertRaises(ValueError):
                prepare_private_upload(
                    staged_video=video, manifest_path=manifest,
                    inbox_dir=base / "inbox", session_dir=base / "sessions",
                    queue=queue, access_token="token", expected_channel_id="channel",
                    title="Learn Red",
                )
            self.assertEqual(start.call_count, 1)

    def test_corrupt_video_does_not_start_session(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            video = base / "red.mp4"
            video.write_bytes(b"original")
            manifest = base / "red.json"
            manifest.write_text(json.dumps(build_manifest(video, "red-ar")))
            video.write_bytes(b"corrupt")
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            with patch("kidsstudio.pi_staging_handoff.start_session") as start:
                with self.assertRaises(ValueError):
                    prepare_private_upload(
                        staged_video=video, manifest_path=manifest,
                        inbox_dir=base / "inbox", session_dir=base / "sessions",
                        queue=queue, access_token="token", expected_channel_id="channel",
                        title="Learn Red",
                    )
                start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
