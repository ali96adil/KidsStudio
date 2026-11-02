import sqlite3
import tempfile
import unittest
from pathlib import Path

from kidsstudio.owner_media_approval import sha256_video
from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_queue_repair import recover_orphaned_sessions
from kidsstudio.youtube_upload_session import save_session


class OrphanEpisodeGuardTests(unittest.TestCase):
    def test_same_episode_different_session_is_not_auto_enqueued(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / "sessions"
            sessions.mkdir()
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            first = base / "first.mp4"
            second = base / "second.mp4"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            for video in (first, second):
                session = sessions / ("red-ar-" + sha256_video(video)[:16] + ".json")
                save_session(session, session_url="https://www.googleapis.com/upload/session",
                             video_path=video)
            report = recover_orphaned_sessions(queue, sessions, "channel")
            self.assertEqual(report["restored"], 1)
            self.assertEqual(report["skipped"], 1)
            self.assertEqual(recover_orphaned_sessions(queue, sessions, "channel")["restored"], 0)
            with sqlite3.connect(queue.path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pi_upload_jobs").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
