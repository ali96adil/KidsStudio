import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.pi_upload_session_audit import audit_sessions
from kidsstudio.youtube_upload_session import save_session
from kidsstudio.owner_media_approval import sha256_video


class SessionAuditTests(unittest.TestCase):
    def test_corrupt_and_orphaned_are_reported_without_secrets(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            sessions = base / "sessions"
            sessions.mkdir()
            video = base / "render.mp4"
            video.write_bytes(b"original media")
            session = sessions / ("red-" + sha256_video(video)[:16] + ".json")
            secret = "https://www.googleapis.com/upload/secret-session-url"
            save_session(session, session_url=secret, video_path=video)
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            result = audit_sessions(queue, sessions)
            self.assertEqual(result["counts"]["orphaned"], 1)
            self.assertFalse(result["healthy"])
            self.assertNotIn(secret, str(result))
            video.write_bytes(b"corrupted media")
            result = audit_sessions(queue, sessions)
            self.assertEqual(result["counts"]["corrupt"], 1)
            self.assertEqual(result["counts"]["valid"], 0)
            self.assertNotIn(secret, str(result))

    def test_valid_queued_session_is_healthy(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            sessions = base / "sessions"
            sessions.mkdir()
            video = base / "render.mp4"
            video.write_bytes(b"original")
            session = sessions / ("red-" + sha256_video(video)[:16] + ".json")
            save_session(session, session_url="https://www.googleapis.com/upload/secret",
                         video_path=video)
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red", session, "channel")
            result = audit_sessions(queue, sessions)
            self.assertTrue(result["healthy"])
            self.assertEqual(result["counts"]["queued"], 1)


if __name__ == "__main__":
    unittest.main()
