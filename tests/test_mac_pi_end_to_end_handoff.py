"""Offline integration: Mac transfer -> Pi watcher -> upload queue.

No network, no real YouTube upload, no public publishing.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.mac_pi_media_transfer import transfer_to_pi
from kidsstudio.pi_staging_watcher import scan_once
from kidsstudio.pi_upload_queue import PiUploadQueue
from kidsstudio.youtube_upload_session import load_session


class MacPiIntegrationTests(unittest.TestCase):
    def test_mac_to_pi_private_upload_queue(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            staging = base / "staging"
            staging.mkdir()
            render = base / "render.mp4"
            render.write_bytes(b"original kids studio episode")

            def fake_rsync(argv, **kwargs):
                if argv[0] == "ssh":
                    command = argv[-1].split(" ")
                    (staging / Path(command[2]).name).rename(staging / Path(command[3]).name)
                else:
                    source = Path(argv[-2])
                    remote_name = Path(argv[-1].split(":")[-1]).name or source.name
                    shutil.copy2(source, staging / remote_name)

            with patch("kidsstudio.mac_pi_media_transfer.subprocess.run",
                       side_effect=fake_rsync):
                sent = transfer_to_pi(
                    render, episode_id="colors-red-ar",
                    ssh_target="kidsstudio@pi.local",
                    remote_staging_dir="/var/lib/kidsstudio/private-upload/staging",
                    dry_run=False,
                )
            self.assertTrue(sent["transferred"])
            metadata = json.loads(next(staging.glob("*.json")).read_text())
            self.assertEqual(metadata, sent["manifest"])
            self.assertEqual((staging / metadata["filename"]).read_bytes(), render.read_bytes())

            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            token_calls = []
            def token():
                token_calls.append(1)
                return "fake-access-token"

            kwargs = dict(
                staging_dir=staging, inbox_dir=base / "inbox",
                session_dir=base / "sessions", queue=queue,
                token_provider=token, expected_channel_id="expected-channel",
                title_for_episode=lambda episode: "Learn Red",
            )
            with patch("kidsstudio.pi_staging_handoff.start_session",
                       return_value="https://www.googleapis.com/upload/fake-session") as start:
                jobs = scan_once(**kwargs)
                self.assertEqual(len(jobs), 1)
                self.assertEqual(scan_once(**kwargs), [])
                start.assert_called_once_with(
                    "fake-access-token", len(render.read_bytes()), "Learn Red", ""
                )
            self.assertEqual(len(token_calls), 1)
            job = queue.claim()
            self.assertEqual(job["episode_id"], "colors-red-ar")
            self.assertEqual(job["channel_id"], "expected-channel")
            saved = load_session(job["session_path"])
            self.assertEqual(Path(saved["video_path"]).read_bytes(), render.read_bytes())

    def test_corrupted_transfer_never_requests_oauth(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            staging = base / "staging"
            staging.mkdir()
            render = base / "render.mp4"
            render.write_bytes(b"original")
            def fake_rsync(argv, **kwargs):
                if argv[0] == "ssh":
                    command = argv[-1].split(" ")
                    (staging / Path(command[2]).name).rename(staging / Path(command[3]).name)
                else:
                    source = Path(argv[-2])
                    remote_name = Path(argv[-1].split(":")[-1]).name or source.name
                    shutil.copy2(source, staging / remote_name)
            with patch("kidsstudio.mac_pi_media_transfer.subprocess.run",
                       side_effect=fake_rsync):
                transfer_to_pi(
                    render, episode_id="colors-red-ar",
                    ssh_target="kidsstudio@pi.local",
                    remote_staging_dir="/var/lib/kidsstudio/private-upload/staging",
                    dry_run=False,
                )
            video = next(staging.glob("*.mp4"))
            video.write_bytes(b"damaged!")
            queue = PiUploadQueue(base / "queue.sqlite")
            queue.initialize()
            with patch("kidsstudio.pi_staging_handoff.start_session") as start:
                result = scan_once(
                    staging_dir=staging, inbox_dir=base / "inbox",
                    session_dir=base / "sessions", queue=queue,
                    token_provider=lambda: "fake-token",
                    expected_channel_id="expected-channel",
                    title_for_episode=lambda episode: "Learn Red",
                )
                self.assertEqual(result, [])
                start.assert_not_called()
            self.assertIsNone(queue.claim())


if __name__ == "__main__":
    unittest.main()
