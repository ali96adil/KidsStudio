"""M68 transfer must require a matching content-QA receipt."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.m67_master_handoff import inventory
from kidsstudio.m68_short_pi_transfer import transfer_approved_short, ShortTransferError


class ShortPiTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / "short.mp4"
        self.video.write_bytes(b"short-video")
        self.manifest = inventory(self.root, master=self.video, episode_id="episode-short-01")
        self.manifest.update({"short_id": "episode-short-01",
                              "source_episode_id": "episode",
                              "status": "SHORT_HASH_PINNED_CONTENT_QA_PENDING"})
        self.receipt = {"decision": "PASS", "short_id": "episode-short-01",
                        "source_episode_id": "episode",
                        "video_sha256": hashlib.sha256(b"short-video").hexdigest()}

    def test_pending_qa_blocks_transfer(self):
        receipt = dict(self.receipt, decision="PENDING")
        with patch("kidsstudio.m68_short_pi_transfer.transfer") as transfer:
            with self.assertRaises(ShortTransferError):
                transfer_approved_short(self.root, self.manifest, receipt,
                                        host="pi.local", user="pi", remote_dir="/incoming")
            transfer.assert_not_called()

    def test_changed_video_blocks_transfer(self):
        self.video.write_bytes(b"changed")
        with patch("kidsstudio.m68_short_pi_transfer.transfer") as transfer:
            with self.assertRaises(Exception):
                transfer_approved_short(self.root, self.manifest, self.receipt,
                                        host="pi.local", user="pi", remote_dir="/incoming")
            transfer.assert_not_called()

    def test_approved_short_uses_existing_transfer(self):
        with patch("kidsstudio.m68_short_pi_transfer.transfer",
                   return_value={"status": "TRANSFERRED_TO_PI_HASH_VERIFIED"}) as transfer:
            result = transfer_approved_short(self.root, self.manifest, self.receipt,
                                             host="pi.local", user="pi",
                                             remote_dir="/incoming")
            transfer.assert_called_once()
            self.assertEqual(result["status"], "SHORT_TRANSFERRED_TO_PI_PRIVATE_STAGING")
            self.assertFalse(result["youtube_upload_authorized"])
            self.assertFalse(result["public_release_authorized"])
