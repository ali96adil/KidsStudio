"""M67 stage readiness recognizes the actual production receipts."""
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m67_readiness_summary import readiness


class StageReceiptTests(unittest.TestCase):
    def test_real_worker_statuses_are_recognized(self):
        receipts = {
            "jobs.json": "MEDIA_JOBS_PREPARED_NOT_GENERATED",
            "comfy_batch_report.json": "IMAGES_GENERATED_PENDING_QA",
            "voice_batch_report.json": "VOICES_GENERATED_PENDING_QA",
            "media_inspection.json": "MEDIA_STRUCTURALLY_READY_PENDING_QA",
            "media_decode_report.json": "MEDIA_DECODED_PENDING_QA",
            "reviewed_manifest.json": "ASSETS_QA_READY_FOR_RENDER",
            "master_inventory.json": "MASTER_INVENTORIED_NOT_TRANSFERRED",
            "pi_transfer_report.json": "TRANSFERRED_TO_PI_HASH_VERIFIED",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, status in receipts.items():
                (root / name).write_text(json.dumps({"status": status}))
            result = readiness(root)
            self.assertEqual(result["incomplete_stages"], [])
            self.assertFalse(result["pi_private_upload_confirmed"])
            self.assertFalse(result["public_release_authorized"])
