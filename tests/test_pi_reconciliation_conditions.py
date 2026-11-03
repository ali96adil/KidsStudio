import tempfile
import unittest
from pathlib import Path

from kidsstudio.pi_session_reconciliation import reconciliation_report
from kidsstudio.pi_upload_queue import PiUploadQueue


class ReconciliationConditionTests(unittest.TestCase):
    def test_conditions_are_privacy_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir()
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            corrupt = sessions / "bad.json"
            corrupt.write_text("sensitive-invalid-content")
            outside = root / "outside.json"
            outside.write_text("secret")
            queue.enqueue("missing-ar", sessions / "missing.json", "channel")
            queue.enqueue("corrupt-ar", corrupt, "channel")
            queue.enqueue("untrusted-ar", outside, "channel")
            report = reconciliation_report(root)
            entries = {item["episode_id"]: item for item in report["episodes"]}
            self.assertEqual(entries["missing-ar"]["session_condition"], "missing")
            self.assertEqual(entries["corrupt-ar"]["session_condition"], "corrupt")
            self.assertEqual(entries["untrusted-ar"]["session_condition"], "untrusted_path")
            self.assertNotIn("sensitive-invalid-content", str(report))
            self.assertNotIn(str(root), str(report))
            self.assertTrue(all(not item["automatic_new_upload_allowed"]
                                for item in report["episodes"]))


if __name__ == "__main__":
    unittest.main()
