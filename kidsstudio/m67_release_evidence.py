"""M67 release evidence manifest: inspect CI and device proof separately.

This module never grants publication and does not upload media.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_readiness_summary import readiness


def report(root, *, commit_sha=None, ci=None, godot=None):
    production = readiness(root)
    checks = {
        "commit_sha_valid": isinstance(commit_sha, str) and len(commit_sha) == 40
            and all(ch in "0123456789abcdef" for ch in commit_sha),
        "ci_success": ci == "success",
        "godot_smoke_success": godot == "success",
        "production_receipts_complete": not production["incomplete_stages"],
    }
    return {
        "status": "M67_SOFTWARE_EVIDENCE_READY_HARDWARE_PENDING"
                  if all(checks.values()) else "M67_SOFTWARE_EVIDENCE_INCOMPLETE",
        "checks": checks,
        "production": production,
        "real_mac_render_verified": False,
        "real_pi_transfer_verified": False,
        "youtube_private_upload_verified": False,
        "owner_private_review_verified": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--commit-sha")
    p.add_argument("--ci")
    p.add_argument("--godot")
    args = p.parse_args(argv)
    result = report(args.root, commit_sha=args.commit_sha,
                    ci=args.ci, godot=args.godot)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "M67_SOFTWARE_EVIDENCE_READY_HARDWARE_PENDING" else 2


if __name__ == "__main__":
    raise SystemExit(main())
