"""Tests for M68 resumable transfer and mandatory M65 handoff."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_master_handoff import inventory
from kidsstudio.m68_short_resume import resume_short, ShortResumeError


class ShortResumeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        video = self.root / "short.mp4"
        video.write_bytes(b"short-payload")
        self.manifest = inventory(self.root, master=video, episode_id="episode-short-01")
        self.manifest.update(short_id="episode-short-01", source_episode_id="episode",
                             status="SHORT_HASH_PINNED_CONTENT_QA_PENDING")
        self.digest = hashlib.sha256(b"short-payload").hexdigest()
        self.qa = {"decision": "PASS", "short_id": "episode-short-01",
                   "source_episode_id": "episode", "video_sha256": self.digest}

    def call_resume(self, receipt=None):
        return resume_short(self.root, self.manifest,
                            self.qa if receipt is None else receipt,
                            host="pi.local", user="pi", remote_dir="/incoming")

    def test_qa_pending_rejected_before_transfer(self):
        with patch("kidsstudio.m68_short_resume.transfer_resumable") as transfer:
            with self.assertRaises(ShortResumeError):
                self.call_resume(dict(self.qa, decision="PENDING"))
            transfer.assert_not_called()

    def test_already_transferred_is_not_upload_authorized(self):
        with patch("kidsstudio.m68_short_resume.transfer_resumable",
                   return_value={"status": "ALREADY_TRANSFERRED_HASH_VERIFIED",
                                 "sha256": self.digest, "remote_master": "/incoming/short.mp4"}):
            report = self.call_resume()
        self.assertEqual(report["status"], "SHORT_PI_STAGED_REQUIRES_M65_INBOX")
        self.assertFalse(report["youtube_upload_authorized"])
        self.assertFalse(report["public_release_authorized"])
        self.assertEqual(report["transfer_status"], "ALREADY_TRANSFERRED_HASH_VERIFIED")

    def test_wrong_remote_hash_rejected(self):
        with patch("kidsstudio.m68_short_resume.transfer_resumable",
                   return_value={"status": "TRANSFERRED_TO_PI_HASH_VERIFIED",
                                 "sha256": "0" * 64, "remote_master": "/incoming/short.mp4"}):
            with self.assertRaises(ShortResumeError):
                self.call_resume()
