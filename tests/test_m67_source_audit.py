"""M67 source audit tests."""
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_source_audit import audit_sources


class SourceAuditTests(unittest.TestCase):
    def test_syntax_error_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "kidsstudio"
            package.mkdir()
            (root / "tests").mkdir()
            (package / "m67_bad.py").write_text("def broken(:\n")
            result = audit_sources(root)
            self.assertEqual(result["status"], "M67_SYNTAX_BLOCKED")

    def test_valid_source_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "kidsstudio"
            package.mkdir()
            (root / "tests").mkdir()
            (package / "m67_ok.py").write_text("value = 1\n")
            result = audit_sources(root)
            self.assertEqual(result["status"], "M67_SYNTAX_PASS")
