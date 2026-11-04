"""M67 Pi read-only audit tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m67_pi_readonly_audit import audit


class PiReadonlyAuditTests(unittest.TestCase):
    def test_missing_deployment_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = audit(db=root / "none.sqlite",
                           inbox_root=root / "inbox",
                           journal=root / "journal.sqlite",
                           render_job_id="a" * 32)
            self.assertEqual(result["status"], "PI_READONLY_BLOCKED")
            self.assertFalse(result["network_used"])

    def test_missing_policy_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "inbox"
            inbox.mkdir(mode=0o700)
            db = root / "queue.sqlite"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE studio_pi_ordinary_media (id TEXT)")
            result = audit(db=db, inbox_root=inbox,
                           journal=root / "journal.sqlite",
                           render_job_id="a" * 32)
            self.assertFalse(result["checks"]["owner_policy_schema"])
            self.assertEqual(result["status"], "PI_READONLY_BLOCKED")
