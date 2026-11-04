"""M68 final audit tests; only existing M65 can authorize private upload."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m68_release_audit import audit


class ReleaseAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "short.mp4"
        self.video.write_bytes(b"sample short")
        self.digest = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.short = {"short_id": "e-short-01", "source_episode_id": "e"}
        self.plan = {"episode_id": "e", "shorts": [self.short]}
        self.qualification = {"episode_id": "e", "shorts": [{
            "short_id": "e-short-01",
            "decode": {"status": "SHORT_FULLY_DECODED_PENDING_CONTENT_QA",
                       "full_decode": "PASS", "video_sha256": self.digest},
            "handoff": {"short_id": "e-short-01", "source_episode_id": "e",
                        "episode_id": "e-short-01",
                        "master": {"relative_path": "short.mp4",
                                   "bytes": self.video.stat().st_size,
                                   "sha256": self.digest}}}]}
        self.qa = {"e-short-01": {"short_id": "e-short-01",
                                 "source_episode_id": "e",
                                 "content_qa": "PASS",
                                 "video_sha256": self.digest,
                                 "youtube_visibility": "PRIVATE_ONLY"}}
        self.imports = {"e-short-01": {
            "status": "M68_SHORT_ACCEPTED_IN_M65_INBOX_NOT_UPLOADED",
            "short_id": "e-short-01", "master_sha256": self.digest}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_qa_and_import_block(self):
        result = audit(self.root, self.plan, self.qualification)
        self.assertEqual(result["status"], "M68_INTEGRATION_BLOCKED")
        self.assertGreaterEqual(len(result["blockers"]), 2)

    def test_complete_evidence_still_never_authorizes_upload(self):
        result = audit(self.root, self.plan, self.qualification, self.qa, self.imports)
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["youtube_upload_authorized"])
        self.assertFalse(result["public_release_authorized"])

    def test_tampering_blocks(self):
        self.video.write_bytes(b"tampered")
        result = audit(self.root, self.plan, self.qualification, self.qa, self.imports)
        self.assertTrue(any("LOCAL_MASTER_CHANGED" in item for item in result["blockers"]))
