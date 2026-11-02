import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_media_inbox import build_manifest
from kidsstudio.pi_staging_handoff import prepare_private_upload
from kidsstudio.pi_upload_queue import PiUploadQueue


class ConcurrentHandoffTests(unittest.TestCase):
    def test_simultaneous_handoffs_create_one_youtube_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            staging.mkdir()
            sessions = root / "sessions"
            sessions.mkdir(mode=0o700)
            inbox = root / "inbox"
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            video = root / "source.mp4"
            video.write_bytes(b"rendered media")
            manifest = build_manifest(video, "red-ar")
            staged = staging / manifest["filename"]
            staged.write_bytes(video.read_bytes())
            metadata = staging / (staged.stem + ".json")
            metadata.write_text(json.dumps(manifest))
            barrier = threading.Barrier(2)

            def handoff(_):
                barrier.wait(timeout=10)
                try:
                    return prepare_private_upload(
                        staged_video=staged, manifest_path=metadata,
                        inbox_dir=inbox, session_dir=sessions, queue=PiUploadQueue(queue.path),
                        access_token="offline", expected_channel_id="channel",
                        title="Learn Red",
                    )
                except ValueError:
                    return None

            with patch("kidsstudio.pi_staging_handoff.start_session",
                       return_value="https://www.googleapis.com/upload/session") as start:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(handoff, range(2)))
            self.assertEqual(sum(result is not None for result in results), 1)
            start.assert_called_once()
            self.assertEqual(len(list(sessions.glob("*.json"))), 1)
            self.assertEqual(len(list((sessions / ".episode-locks").glob("*.lock"))), 1)
            import sqlite3
            with sqlite3.connect(queue.path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pi_upload_jobs").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
