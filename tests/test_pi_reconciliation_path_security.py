import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kidsstudio.pi_session_reconciliation import reconciliation_report
from kidsstudio.pi_upload_queue import PiUploadQueue


class ReconciliationPathSecurityTests(unittest.TestCase):
    def test_queue_path_outside_sessions_is_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir()
            outside = root / "outside.json"
            outside.write_text("do-not-read")
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red-ar", outside, "channel")
            with patch("kidsstudio.pi_session_reconciliation.load_session",
                       side_effect=AssertionError("outside file was read")):
                report = reconciliation_report(root)
            entry = report["episodes"][0]
            self.assertFalse(entry["session_saved"])
            self.assertFalse(entry["session_valid"])
            self.assertEqual(entry["action"], "manual_reconcile_youtube_before_retry")
            self.assertNotIn("do-not-read", str(report))
            self.assertNotIn(str(outside), str(report))

    def test_symlink_inside_sessions_is_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir()
            outside = root / "secret.json"
            outside.write_text("secret")
            link = sessions / "linked.json"
            link.symlink_to(outside)
            queue = PiUploadQueue(root / "queue.sqlite")
            queue.initialize()
            queue.enqueue("red-ar", link, "channel")
            with patch("kidsstudio.pi_session_reconciliation.load_session",
                       side_effect=AssertionError("symlink was read")):
                report = reconciliation_report(root)
            self.assertFalse(report["episodes"][0]["session_valid"])


if __name__ == "__main__":
    unittest.main()
