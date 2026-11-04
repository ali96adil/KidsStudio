"""M68 import delegation tests: no upload and no bypass of M65 acceptance."""
import unittest
from unittest.mock import patch

from kidsstudio.m68_pi_short_import import import_short


RECEIPT = {"status": "SHORT_ON_PI_PENDING_PRIVATE_UPLOAD",
           "short_id": "colors-ar-001-short-01",
           "source_episode_id": "colors-ar-001",
           "sha256": "a" * 64,
           "youtube_upload_authorized": False,
           "public_release_authorized": False}


class ShortImportTests(unittest.TestCase):
    def test_delegates_to_existing_inbox(self):
        seen = []
        def importer(*args, **kwargs):
            seen.append(kwargs)
            return {"status": "M67_IMPORTED_VIA_M65_ORDINARY_INBOX",
                    "master_sha256": RECEIPT["sha256"]}
        with patch("kidsstudio.m68_pi_short_import.assess_short_import",
                   return_value={"status": "M68_SHORT_READY_FOR_EXISTING_M65_IMPORT"}):
            result = import_short(None, "/srv/inbox", transfer_receipt=RECEIPT,
                                  transferred_master="/srv/incoming/short.mp4",
                                  plan_file="/srv/plan.json",
                                  readiness_file="/srv/ready.json",
                                  render_job_id="short-job-01", importer=importer)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["expected_sha256"], RECEIPT["sha256"])
        self.assertFalse(result["youtube_uploaded"])
        self.assertFalse(result["public_release_authorized"])

    def test_rejects_wrong_m65_digest(self):
        with patch("kidsstudio.m68_pi_short_import.assess_short_import",
                   return_value={"status": "M68_SHORT_READY_FOR_EXISTING_M65_IMPORT"}):
            with self.assertRaises(RuntimeError):
                import_short(None, "/srv/inbox", transfer_receipt=RECEIPT,
                             transferred_master="/srv/incoming/short.mp4",
                             plan_file="/srv/plan.json",
                             readiness_file="/srv/ready.json",
                             render_job_id="short-job-01",
                             importer=lambda *a, **k: {
                                 "status": "M67_IMPORTED_VIA_M65_ORDINARY_INBOX",
                                 "master_sha256": "b" * 64})
