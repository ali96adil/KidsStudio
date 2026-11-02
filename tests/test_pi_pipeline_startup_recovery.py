import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_pipeline_service import run_pipeline
from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.youtube_upload_session import save_session
from kidsstudio.owner_media_approval import sha256_video


class StartupRecoveryTests(unittest.TestCase):
    def test_orphan_session_restored_before_pipeline_tick(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            state = base / "private-upload"
            state.mkdir(mode=0o700)
            sessions = state / "sessions"
            sessions.mkdir(mode=0o700)
            video = base / "red.mp4"
            video.write_bytes(b"rendered video")
            session = sessions / ("red-ar-" + sha256_video(video)[:16] + ".json")
            save_session(session, session_url="https://www.googleapis.com/upload/session",
                         video_path=video)
            credentials = base / "youtube.json"
            credentials.write_text(json.dumps({
                "client_id": "test", "client_secret": "test",
                "refresh_token": "test", "channel_id": "channel",
            }))
            credentials.chmod(0o600)
            titles = base / "titles.json"
            titles.write_text(json.dumps({"red-ar": "Learn Red"}))
            with patch("kidsstudio.pi_pipeline_service.pipeline_tick") as tick:
                result = run_pipeline(
                    state_dir=state, credentials=credentials,
                    titles_file=titles, once=True,
                )
            self.assertEqual(result, 0)
            tick.assert_called_once()
            queue = PiUploadQueue(state / "queue.sqlite")
            self.assertEqual(queue.claim()["episode_id"], "red-ar")


if __name__ == "__main__":
    unittest.main()
