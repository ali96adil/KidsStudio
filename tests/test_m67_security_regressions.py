"""M67 regression tests for file safety and fail-closed Pi audit."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m67_master_handoff import HandoffError, inventory, verify_inventory
from kidsstudio.m67_pi_readonly_audit import audit


class SecurityRegressionTests(unittest.TestCase):
    def test_symlinked_master_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actual = root / "real.mp4"
            actual.write_bytes(b"media")
            alias = root / "alias.mp4"
            alias.symlink_to(actual)
            with self.assertRaises(HandoffError):
                inventory(root, master=alias, episode_id="colors-ar-001")

    def test_symlinked_parent_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "actual"
            directory.mkdir()
            (directory / "master.mp4").write_bytes(b"media")
            (root / "alias").symlink_to(directory, target_is_directory=True)
            with self.assertRaises(HandoffError):
                verify_inventory(root, {
                    "episode_id": "colors-ar-001",
                    "master": {"relative_path": "alias/master.mp4",
                               "bytes": 5, "sha256": "0" * 64}})

    def test_missing_journal_never_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox"
            inbox.mkdir(mode=0o700)
            db = root / "queue.sqlite"
            with sqlite3.connect(db) as connection:
                connection.execute(
                    "CREATE TABLE studio_pi_ordinary_media (id TEXT)")
                connection.execute(
                    "CREATE TABLE studio_youtube_private_policies (id TEXT)")
            result = audit(db=db, inbox_root=inbox,
                           journal=root / "missing.sqlite",
                           render_job_id="a" * 32)
            self.assertFalse(result["checks"]["journal_readable"])
            self.assertEqual(result["status"], "PI_READONLY_BLOCKED")
