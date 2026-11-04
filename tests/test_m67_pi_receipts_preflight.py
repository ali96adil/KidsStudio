"""M67 receipt validation tests."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_pi_receipts_preflight import preflight
from kidsstudio.youtube_private_upload import file_sha256


class ReceiptTests(unittest.TestCase):
    def test_matching_receipts_still_need_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            movie = root / "movie.mp4"
            ready = root / "ready.json"
            plan = root / "plan.json"
            movie.write_bytes(b"fixture")
            ready.write_text('{"ready":true}')
            digest = file_sha256(movie)
            job = "a" * 32
            plan.write_text(json.dumps({
                "render_job_id": job, "master_sha256": digest,
                "readiness_sha256": file_sha256(ready)}))
            result = preflight(master=movie, plan=plan, readiness=ready,
                               render_job_id=job, expected_sha256=digest)
            self.assertEqual(result["status"],
                             "M67_PI_RECEIPTS_CONSISTENT_NEEDS_M65_APPROVAL")
            self.assertFalse(result["youtube_uploaded"])

    def test_mismatched_readiness_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            movie = root / "movie.mp4"
            ready = root / "ready.json"
            plan = root / "plan.json"
            movie.write_bytes(b"fixture")
            ready.write_text("{}")
            digest = file_sha256(movie)
            plan.write_text(json.dumps({
                "render_job_id": "a" * 32, "master_sha256": digest,
                "readiness_sha256": "0" * 64}))
            result = preflight(master=movie, plan=plan, readiness=ready,
                               render_job_id="a" * 32, expected_sha256=digest)
            self.assertEqual(result["status"], "M67_PI_RECEIPTS_BLOCKED")
