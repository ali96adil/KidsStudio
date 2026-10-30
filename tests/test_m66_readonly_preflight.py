"""Offline tests for M66 read-only preflight; no Pi, Google or network."""
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from kidsstudio.m66_readonly_preflight import inspect


class M66ReadOnlyPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "studio.db"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE sample (id INTEGER)")
        self.inbox = self.root / "inbox"
        self.inbox.mkdir()
        self.journal = self.root / "journal.json"
        self.fixture = self.root / "fixture.mp4"
        self.fixture.write_bytes(b"synthetic test bytes")

    def run_check(self, **kwargs):
        return inspect(db=self.db, inbox=self.inbox, journal=self.journal,
                       **kwargs)

    def test_initial_station_does_not_create_journal(self):
        result = self.run_check()
        self.assertTrue(result["passed"], result)
        self.assertFalse(self.journal.exists())
        self.assertFalse(result["upload_attempted"])

    def test_fixture_hash_matches(self):
        digest = hashlib.sha256(self.fixture.read_bytes()).hexdigest()
        result = self.run_check(fixture=self.fixture, expected_sha256=digest)
        self.assertTrue(result["passed"], result)

    def test_fixture_hash_mismatch_blocks(self):
        result = self.run_check(fixture=self.fixture, expected_sha256="0" * 64)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["fixture_sha256"]["ok"])

    def test_symlink_inbox_blocks(self):
        self.inbox.rmdir()
        self.inbox.symlink_to(self.root, target_is_directory=True)
        result = self.run_check()
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["inbox"]["ok"])

    def test_missing_database_blocks(self):
        self.db.unlink()
        self.assertFalse(self.run_check()["passed"])


if __name__ == "__main__":
    unittest.main()
