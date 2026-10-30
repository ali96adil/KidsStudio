"""M67 validate all three Pi transfer receipts before invoking M65 import.

This is read-only: it never inserts an upload or grants publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .youtube_private_upload import file_sha256


HEX = re.compile(r"^[0-9a-f]{64}$")
JOB = re.compile(r"^[0-9a-f]{32}$")


def preflight(*, master, plan, readiness, render_job_id, expected_sha256):
    checks = {}
    for name, path in (("master", master), ("plan", plan), ("readiness", readiness)):
        path = Path(path)
        checks[name + "_file"] = path.is_file() and not path.is_symlink()
    checks["job_id_format"] = isinstance(render_job_id, str) and bool(JOB.fullmatch(render_job_id))
    checks["master_hash_format"] = (isinstance(expected_sha256, str)
                                    and bool(HEX.fullmatch(expected_sha256)))
    if all(checks.values()):
        checks["master_hash_match"] = file_sha256(master) == expected_sha256
        try:
            document = json.loads(Path(plan).read_text(encoding="utf-8"))
            checks["plan_job_match"] = document.get("render_job_id") == render_job_id
            checks["plan_master_match"] = document.get("master_sha256") == expected_sha256
            checks["readiness_hash_match"] = (
                document.get("readiness_sha256") == file_sha256(readiness))
        except (ValueError, OSError, AttributeError):
            checks["plan_job_match"] = False
            checks["plan_master_match"] = False
            checks["readiness_hash_match"] = False
    return {"status": "M67_PI_RECEIPTS_CONSISTENT_NEEDS_M65_APPROVAL"
            if all(checks.values()) else "M67_PI_RECEIPTS_BLOCKED",
            "checks": checks, "youtube_uploaded": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("master", "plan", "readiness"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--render-job-id", required=True)
    p.add_argument("--sha256", required=True)
    args = p.parse_args(argv)
    result = preflight(master=args.master, plan=args.plan,
                       readiness=args.readiness,
                       render_job_id=args.render_job_id,
                       expected_sha256=args.sha256)
    print(json.dumps(result, indent=2))
    return 0 if result["status"].startswith("M67_PI_RECEIPTS_CONSISTENT") else 2


if __name__ == "__main__":
    raise SystemExit(main())
