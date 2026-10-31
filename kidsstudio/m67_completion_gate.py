"""M67 completion gate: distinguish software evidence from real hardware proof.

Offline checks are valuable but cannot certify Mac, Pi, OAuth or YouTube.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_readiness_summary import readiness


REQUIRED = ("mac_render_verified", "pi_transfer_verified",
            "m65_pi_inbox_accepted", "private_youtube_video_verified",
            "owner_private_review_completed")


def evaluate(root, acceptance=None):
    production = readiness(root)
    evidence = acceptance if isinstance(acceptance, dict) else {}
    checks = {key: evidence.get(key) is True for key in REQUIRED}
    # This report cannot verify arbitrary claimed evidence; external operator
    # must inspect receipts and actual devices before treating these as facts.
    return {
        "status": "M67_HARDWARE_EVIDENCE_REPORTED_NEEDS_INDEPENDENT_VERIFICATION"
                  if all(checks.values()) and not production["incomplete_stages"]
                  else "M67_NOT_ACCEPTED",
        "production": production,
        "hardware_claims": checks,
        "missing": [name for name, value in checks.items() if not value],
        "hardware_independently_verified": False,
        "youtube_upload_performed": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--acceptance", type=Path)
    args = p.parse_args(argv)
    claims = json.loads(args.acceptance.read_text(encoding="utf-8")) if args.acceptance else None
    result = evaluate(args.root, claims)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] != "M67_NOT_ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
