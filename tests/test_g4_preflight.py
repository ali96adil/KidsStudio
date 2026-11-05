import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.g4_preflight import inspect_environment, main
from kidsstudio.studio_queue import StudioQueue


class G4PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.database = self.root / "queue.sqlite"
        StudioQueue(self.database).initialize()

    def inspect(self):
        return inspect_environment(artifact_root=self.artifacts, db_path=self.database)

    def test_read_only_preflight_preserves_database(self):
        before = self.database.read_bytes()
        with patch("kidsstudio.g4_preflight.shutil.disk_usage") as usage:
            usage.return_value.free = 2 * 1024 ** 3
            report = self.inspect()
        self.assertEqual(report["status"], "PREFLIGHT_PASS_NOT_LIVE_QUALIFIED")
        self.assertFalse(report["publication_approved"])
        self.assertEqual(self.database.read_bytes(), before)

    def test_missing_database_blocks_without_creating_it(self):
        self.database.unlink()
        report = self.inspect()
        self.assertEqual(report["status"], "PREFLIGHT_BLOCKED")
        self.assertFalse(self.database.exists())

    def test_git_root_blocks_preflight(self):
        (self.root / ".git").mkdir()
        self.assertFalse(self.inspect()["checks"]["artifact_root_outside_git"])
        self.assertEqual(self.inspect()["status"], "PREFLIGHT_BLOCKED")

    def test_corrupt_database_blocks(self):
        self.database.write_bytes(b"not a sqlite database")
        report = self.inspect()
        self.assertFalse(report["checks"]["sqlite_integrity"])

    def test_cli_redacts_local_paths(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(["--artifact-root", str(self.artifacts),
                              "--db", str(self.root / "missing.sqlite")])
        self.assertEqual(exit_code, 1)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertFalse(json.loads(output.getvalue())["publication_approved"])


if __name__ == "__main__":
    unittest.main()
