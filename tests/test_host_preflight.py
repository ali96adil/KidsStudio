import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.host_preflight import inspect_host, main


class HostPreflightTests(unittest.TestCase):
    def test_empty_options_never_grant_production(self):
        result = inspect_host()
        self.assertTrue(result["read_only"])
        self.assertFalse(result["production_approved"])
        self.assertIn("python_supported", result["checks"])

    def test_missing_paths_report_action_required(self):
        with tempfile.TemporaryDirectory() as directory:
            result = inspect_host(
                artifact_root=str(Path(directory) / "missing"),
                queue_db=str(Path(directory) / "missing.sqlite"))
            self.assertEqual(result["status"], "PREFLIGHT_ACTION_REQUIRED")
            self.assertFalse(result["checks"]["queue_exists"])
            self.assertFalse(result["checks"]["artifact_root_exists"])

    def test_existing_paths_are_never_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "state.sqlite"
            db.write_bytes(b"not a real sqlite db")
            before = db.read_bytes()
            result = inspect_host(artifact_root=str(root), queue_db=str(db),
                                  minimum_free_gib=0)
            self.assertEqual(db.read_bytes(), before)
            self.assertTrue(result["checks"]["queue_nonempty"])
            self.assertFalse(result["production_approved"])

    def test_git_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            result = inspect_host(artifact_root=str(root), minimum_free_gib=0)
            self.assertFalse(result["checks"]["artifact_outside_git"])

    def test_cli_error_redacts_paths(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--minimum-free-gib", "-1",
                         "--artifact-root", "/private/sensitive"])
        self.assertEqual(code, 2)
        self.assertNotIn("/private/sensitive", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status"], "PREFLIGHT_ERROR")


if __name__ == "__main__":
    unittest.main()
