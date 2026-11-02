import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_upload_dashboard import render_upload_dashboard, upload_snapshot
from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.youtube_upload_session import save_session
from kidsstudio.owner_media_approval import sha256_video


class UploadDashboardTests(unittest.TestCase):
    def test_counts_and_private_html(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            sessions = base / "sessions"
            sessions.mkdir()
            video = base / "video.mp4"
            video.write_bytes(b"video")
            session = sessions / ("red-" + sha256_video(video)[:16] + ".json")
            secret = "https://www.googleapis.com/upload/secret-token"
            save_session(session, session_url=secret, video_path=video)
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            job = queue.enqueue("red", session, "channel")
            claimed = queue.claim()
            self.assertEqual(claimed["id"], job)
            queue.finish(job, success=False)
            data = upload_snapshot(queue, sessions)
            self.assertEqual(data["queue"]["failed"], 1)
            self.assertEqual(data["sessions"]["counts"]["failed"], 1)
            html = render_upload_dashboard(data)
            self.assertIn("Attention required", html)
            self.assertIn("Corrupt sessions", html)
            self.assertNotIn(secret, html)
            self.assertNotIn(str(video), html)
            self.assertNotIn("channel", html)


if __name__ == "__main__":
    unittest.main()
