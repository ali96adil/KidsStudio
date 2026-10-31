"""M68 transfer authorization tests without network access."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m68_short_transfer import transfer_approved_short, ShortTransferError


class ShortTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "short.mp4"
        self.video.write_bytes(b"short media bytes")
        digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.handoff = {
            "episode_id": "colors-ar-001-short-01",
            "short_id": "colors-ar-001-short-01",
            "source_episode_id": "colors-ar-001",
            "status": "SHORT_HASH_PINNED_CONTENT_QA_PENDING",
            "master": {"relative_path": "short.mp4", "bytes": self.video.stat().st_size,
                       "sha256": digest},
            "public_release_authorized": False, "youtube_upload_authorized": False,
        }
        self.qa = {"short_id": self.handoff["short_id"],
                   "source_episode_id": self.handoff["source_episode_id"],
                   "video_sha256": digest, "content_qa": "PASS",
                   "youtube_visibility": "PRIVATE_ONLY"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_failed_content_qa_blocks_transport(self):
        self.qa["content_qa"] = "FAIL"
        called = []
        with self.assertRaises(ShortTransferError):
            transfer_approved_short(self.root, self.handoff, self.qa,
                                    host="pi.local", user="pi", remote_dir="/srv/incoming",
                                    transport=lambda *a, **k: called.append(True))
        self.assertFalse(called)

    def test_approved_content_qa_reuses_transport(self):
        calls = []
        def fake_transport(root, handoff, **kwargs):
            calls.append(kwargs)
            return {"status": "TRANSFERRED_TO_PI_HASH_VERIFIED",
                    "remote_master": "/srv/incoming/short.mp4",
                    "sha256": handoff["master"]["sha256"]}
        result = transfer_approved_short(self.root, self.handoff, self.qa,
                                         host="pi.local", user="pi",
                                         remote_dir="/srv/incoming",
                                         transport=fake_transport)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "SHORT_ON_PI_PENDING_PRIVATE_UPLOAD")
        self.assertFalse(result["youtube_upload_authorized"])

    def test_changed_file_blocks_transport(self):
        self.video.write_bytes(b"changed")
        with self.assertRaises(Exception):
            transfer_approved_short(self.root, self.handoff, self.qa,
                                    host="pi.local", user="pi", remote_dir="/srv/incoming",
                                    transport=lambda *a, **k: self.fail("must not transfer"))
