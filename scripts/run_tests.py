#!/usr/bin/env python3
"""Run the complete unit suite with a canonical temporary directory.

macOS exposes its per-user temporary directory through ``/var``, which is a
system symlink to ``/private/var``. KidsStudio deliberately rejects symlinked
private evidence paths. Canonicalizing only the test runner's temporary root
keeps that production safety contract intact while making the same suite
reproducible on Linux and macOS.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


def canonical_tempdir(value: str) -> str:
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError("test temporary root must be an existing directory")
    return str(path)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    repository_text = str(repository)
    if repository_text not in sys.path:
        sys.path.insert(0, repository_text)
    tempfile.tempdir = canonical_tempdir(tempfile.gettempdir())
    suite = unittest.defaultTestLoader.discover(str(repository / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
