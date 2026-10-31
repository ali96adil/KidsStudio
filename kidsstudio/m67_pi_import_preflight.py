"""M67 Pi import read-only dry-run before staging anything."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_pi_receipts_preflight import preflight
from .m67_pi_readonly_audit import audit


def preflight_import(*, db, inbox_root, journal, render_job_id,
                     master, plan, readiness, expected_sha256):
    receipts = preflight(master=master, plan=plan, readiness=readiness,
                         render_job_id=render_job_id,
                         expected_sha256=expected_sha256)
    deployment = audit(db=db, inbox_root=inbox_root, journal=journal,
                       render_job_id=render_job_id)
    eligible = (
        receipts["status"] == "M67_PI_RECEIPTS_CONSISTENT_NEEDS_M65_APPROVAL"
        and deployment["status"] == "PI_READONLY_READY"
    )
    return {
        "status": ("M67_IMPORT_PREFLIGHT_PASSED_NEEDS_M65_POLICY"
                   if eligible else "M67_IMPORT_PREFLIGHT_BLOCKED"),
        "receipts": receipts, "deployment": deployment,
        "staged_files": False, "network_used": False,
        "youtube_uploaded": False, "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("db", "inbox-root", "journal", "master", "plan", "readiness"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--render-job-id", required=True)
    p.add_argument("--sha256", required=True)
    args = p.parse_args(argv)
    result = preflight_import(
        db=args.db, inbox_root=args.inbox_root, journal=args.journal,
        render_job_id=args.render_job_id, master=args.master,
        plan=args.plan, readiness=args.readiness, expected_sha256=args.sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "M67_IMPORT_PREFLIGHT_PASSED_NEEDS_M65_POLICY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
