"""The test runner may canonicalize test temp paths, never production paths."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.run_tests import canonical_tempdir


class TestRunnerTests(unittest.TestCase):
    def test_symlinked_test_temp_alias_resolves_to_real_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            self.assertEqual(canonical_tempdir(str(alias)), str(real.resolve()))

    def test_regular_file_is_not_a_test_temp_root(self):
        with tempfile.TemporaryDirectory() as folder:
            item = Path(folder) / "item"
            item.write_text("not a directory", encoding="utf-8")
            with self.assertRaises(ValueError):
                canonical_tempdir(str(item))


if __name__ == "__main__":
    unittest.main()
