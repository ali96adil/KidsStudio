import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from kidsstudio.owner_media_approval import sha256_video
from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_queue_repair import recover_orphaned_sessions
from kidsstudio.pi_upload_worker import process_one
from kidsstudio.youtube_upload_session import save_session


class PiRestartIdempotencyTests(unittest.TestCase):
    def test_two_restarts_do_not_duplicate_job_or_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / "sessions"
            sessions.mkdir()
            video = base / "red.mp4"
            video.write_bytes(b"offline test video")
            session = sessions / ("red-ar-" + sha256_video(video)[:16] + ".json")
            save_session(session, session_url="https://www.googleapis.com/upload/session",
                         video_path=video)
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            self.assertEqual(recover_orphaned_sessions(queue, sessions, "channel")["restored"], 1)
            job = queue.claim()
            self.assertIsNotNone(job)
            # Crash before completing upload: recover the same queue job.
            restarted = PiUploadQueue(base / "queue.sqlite")
            self.assertEqual(restarted.recover_interrupted(), 1)
            self.assertEqual(recover_orphaned_sessions(restarted, sessions, "channel")["restored"], 0)
            token = Mock(side_effect=AssertionError("OAuth must not run in offline test"))
            with patch("kidsstudio.pi_upload_worker.supervise_resume",
                       return_value={"recorded_private_upload": True}) as resume:
                outcome = process_one(restarted, object(), token)
            self.assertEqual(outcome["job_id"], job["id"])
            resume.assert_called_once()
            self.assertEqual(restarted.recover_interrupted(), 0)
            self.assertEqual(recover_orphaned_sessions(restarted, sessions, "channel")["restored"], 0)
            with patch("kidsstudio.pi_upload_worker.supervise_resume") as second_resume:
                self.assertIsNone(process_one(restarted, object(), token))
                second_resume.assert_not_called()
            token.assert_not_called()
            with sqlite3.connect(restarted.path) as db:
                states = db.execute("SELECT state FROM pi_upload_jobs").fetchall()
            self.assertEqual(states, [("completed",)])

    def test_failed_job_stays_failed_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / "sessions"
            sessions.mkdir()
            video = base / "red.mp4"
            video.write_bytes(b"offline test video")
            session = sessions / ("red-ar-" + sha256_video(video)[:16] + ".json")
            save_session(session, session_url="https://www.googleapis.com/upload/session",
                         video_path=video)
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red-ar", session, "channel")
            job = queue.claim()
            queue.finish(job["id"], success=False, error="manual reconciliation")
            reopened = PiUploadQueue(base / "queue.sqlite")
            self.assertEqual(reopened.recover_interrupted(), 0)
            self.assertEqual(recover_orphaned_sessions(reopened, sessions, "channel")["restored"], 0)
            with patch("kidsstudio.pi_upload_worker.supervise_resume") as resume:
                self.assertIsNone(process_one(reopened, object(), lambda: "token"))
                resume.assert_not_called()


if __name__ == "__main__":
    unittest.main()
