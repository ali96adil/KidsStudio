"""M66.3 bounded read-only qualification report for Mac/Pi handoff evidence.

Consumes exported JSON evidence, never touches OAuth or media, and refuses
to claim device qualification without independently observed evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED = (
    "mac_sha256", "pi_sha256", "transfer_resumed",
    "mac_off_pi_continued", "pi_reboot_recovered",
    "youtube_privacy_status", "owner_review_status",
)


class QualificationError(ValueError):
    pass


def assess(evidence: dict) -> dict:
    if not isinstance(evidence, dict):
        raise QualificationError("evidence must be a JSON object")
    missing = [key for key in REQUIRED if key not in evidence]
    if missing:
        return {"status": "NOT_QUALIFIED", "missing": missing, "checks": {}}
    checks = {}
    a, b = evidence["mac_sha256"], evidence["pi_sha256"]
    checks["same_media_sha256"] = (
        isinstance(a, str) and isinstance(b, str)
        and len(a) == 64 and a == b
        and all(ch in "0123456789abcdef" for ch in a.lower())
    )
    checks["transfer_resumed"] = evidence["transfer_resumed"] is True
    checks["pi_independent"] = evidence["mac_off_pi_continued"] is True
    checks["reboot_safe"] = evidence["pi_reboot_recovered"] is True
    checks["private_only"] = evidence["youtube_privacy_status"] == "private"
    checks["owner_review"] = evidence["owner_review_status"] in (
        "pending", "approved", "rejected"
    )
    checks["no_duplicate_insert"] = evidence.get("duplicate_inserts") == 0
    checks["no_public_transition"] = evidence.get("public_transitions") == 0
    checks["real_hardware_observed"] = evidence.get("real_hardware_observed") is True
    checks["google_video_id_recorded"] = (
        isinstance(evidence.get("youtube_video_id"), str)
        and len(evidence["youtube_video_id"]) > 0
    )
    return {
        "status": "QUALIFIED" if all(checks.values()) else "NOT_QUALIFIED",
        "checks": checks,
        "missing": [],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.evidence.is_symlink() or not args.evidence.is_file():
            raise QualificationError("regular evidence JSON required")
        result = assess(json.loads(args.evidence.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        result = {"status": "NOT_QUALIFIED", "reason": str(exc)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
