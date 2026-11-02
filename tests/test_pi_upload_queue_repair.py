import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_queue_repair import recover_orphaned_sessions, requeue_failed_job
from kidsstudio.youtube_upload_session import save_session
from kidsstudio.owner_media_approval import sha256_video


class RepairTests(unittest.TestCase):
    def test_recover_orphan_and_prevent_duplicate(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            sessions = base / "sessions"
            sessions.mkdir()
            video = base / "red.mp4"
            video.write_bytes(b"rendered video")
            session = sessions / ("red-ar-" + sha256_video(video)[:16] + ".json")
            save_session(session, session_url="https://www.googleapis.com/upload/session",
                         video_path=video)
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            self.assertEqual(recover_orphaned_sessions(queue, sessions, "channel")["restored"], 1)
            self.assertEqual(recover_orphaned_sessions(queue, sessions, "channel")["restored"], 0)
            job = queue.claim()
            self.assertEqual(job["episode_id"], "red-ar")
            queue.finish(job["id"], success=False)
            self.assertTrue(requeue_failed_job(queue, job["id"]))
            self.assertEqual(queue.claim()["id"], job["id"])
            self.assertFalse(requeue_failed_job(queue, job["id"]))


if __name__ == "__main__":
    unittest.main()
