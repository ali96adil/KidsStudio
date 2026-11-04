"""M66.4 reconciliation: no second insert when status is ambiguous."""
import sqlite3
import tempfile
from pathlib import Path
import unittest

from kidsstudio.m66_upload_reconciliation import classify, inspect_journal


class M66ReconciliationTests(unittest.TestCase):
    def test_started_stops(self):
        self.assertEqual(classify({"state": "STARTED", "video_id": None})["action"],
                         "STOP_NO_SECOND_INSERT")

    def test_uploaded_requires_get(self):
        result = classify({"state": "UPLOADED_UNVERIFIED",
                           "video_id": "abcdefghijk"})
        self.assertEqual(result["action"], "VERIFY_WITH_GET")

    def test_verified_does_not_upload(self):
        result = classify({"state": "PRIVATE_VERIFIED",
                           "video_id": "abcdefghijk"})
        self.assertEqual(result["action"], "NO_UPLOAD")

    def test_unknown_and_invalid_id_stop(self):
        self.assertEqual(classify({"state": "UNKNOWN"})["action"], "STOP")
        self.assertEqual(classify({"state": "PRIVATE_VERIFIED",
                                   "video_id": "bad"})["action"], "STOP")

    def test_readonly_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "upload.sqlite"
            job = "a" * 32
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE attempts(render_job_id TEXT,state TEXT,video_id TEXT)")
                db.execute("INSERT INTO attempts VALUES(?,?,?)",
                           (job, "STARTED", None))
            result = inspect_journal(path, job)
            self.assertEqual(result["status"], "NEEDS_RECONCILIATION")


if __name__ == "__main__":
    unittest.main()
