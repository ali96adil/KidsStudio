"""M67 source integrity preflight for the final candidate.

Compiles every M67 Python module without importing external dependencies.
Can be run on Mac or Pi before installing/running media engines.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def audit_sources(repository):
    root = Path(repository)
    package = root / "kidsstudio"
    tests = root / "tests"
    paths = sorted(package.glob("m67_*.py")) + sorted(tests.glob("test_m67_*.py"))
    results = []
    for path in paths:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            state = "SYNTAX_OK"
        except (SyntaxError, UnicodeError, OSError) as exc:
            state = type(exc).__name__
        results.append({"path": str(path.relative_to(root)), "status": state})
    return {
        "status": "M67_SYNTAX_PASS" if results and all(
            row["status"] == "SYNTAX_OK" for row in results)
            else "M67_SYNTAX_BLOCKED",
        "files_checked": len(results),
        "results": results,
        "hardware_verified": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repository", type=Path, default=Path.cwd())
    args = p.parse_args(argv)
    result = audit_sources(args.repository)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "M67_SYNTAX_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
