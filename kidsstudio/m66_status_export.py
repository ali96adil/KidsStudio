"""M66.5 static operator status export from offline qualification evidence.

Does not host a web service, expose tokens, or read media. JSON can be
consumed by a future authenticated dashboard adapter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m66_qualification_report import assess


def snapshot(evidence: dict) -> dict:
    qualification = assess(evidence)
    checks = qualification.get("checks", {})
    return {
        "schema_version": 1,
        "screen": "KIDS_STUDIO_M66_OWNER_QUALIFICATION",
        "qualification_status": qualification["status"],
        "checks_passed": sum(value is True for value in checks.values()),
        "checks_total": len(checks),
        "missing": qualification.get("missing", []),
        "checks": checks,
        "youtube_upload_allowed_by_this_report": False,
        "public_release_allowed_by_this_report": False,
        "device_test_evidence_required": True,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.evidence.is_symlink() or not args.evidence.is_file():
        p.error("regular evidence JSON required")
    if args.output.is_symlink() or args.output == args.evidence:
        p.error("output must be separate non-symlink file")
    data = json.loads(args.evidence.read_text(encoding="utf-8"))
    result = snapshot(data)
    # Intentionally do not export any raw evidence values (IDs/paths/tokens).
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": result["qualification_status"],
                      "output": str(args.output)}))
    return 0 if result["qualification_status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
