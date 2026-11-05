import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.host_readiness import inspect_host, main


class HostReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.db = self.root / "queue.sqlite"
        self.db.write_bytes(b"synthetic - never opened by probe")

    def test_private_local_root_and_db(self):
        report = inspect_host(artifact_root=self.artifacts, database=self.db,
                              min_free_gib=0)
        self.assertTrue(report["ready_for_supervised_tests"])
        self.assertFalse(report["production_approved"])
        self.assertFalse(report["publication_approved"])
        self.assertEqual(self.db.read_bytes(), b"synthetic - never opened by probe")

    def test_missing_db_not_ready(self):
        report = inspect_host(artifact_root=self.artifacts,
                              database=self.root / "missing.db", min_free_gib=0)
        self.assertFalse(report["checks"]["database_exists"])
        self.assertFalse(report["ready_for_supervised_tests"])

    def test_git_root_rejected(self):
        (self.root / ".git").mkdir()
        report = inspect_host(artifact_root=self.artifacts, min_free_gib=0)
        self.assertFalse(report["checks"]["artifact_root_outside_git"])

    def test_cli_does_not_print_private_paths(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--artifact-root", str(self.artifacts),
                         "--db", str(self.db), "--min-free-gib", "0"])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertFalse(json.loads(output.getvalue())["publication_approved"])

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            inspect_host(artifact_root=self.artifacts, min_free_gib=-1)


if __name__ == "__main__":
    unittest.main()
