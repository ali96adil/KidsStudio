"""Single-command, safe offline acceptance report for Kids Studio Pi.

Never performs network access, YouTube uploads or public releases.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .pi_offline_trial import run_offline_trial


def build_acceptance_report() -> dict:
    trial = run_offline_trial()
    checks = {
        "pi_first_boot": trial["first_boot_exit_code"] == 0,
        "real_empty_pipeline_tick": trial["real_pipeline_tick"] is True,
        "zero_oauth_calls": trial["oauth_calls"] == 0,
        "zero_upload_calls": trial["upload_calls"] == 0,
        "zero_resume_calls": trial["resume_calls"] == 0,
        "local_readiness": trial["readiness"]["ready_for_hardware_test"] is True,
        "no_public_release": trial["public_release_enabled"] is False,
    }
    return {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "passed": all(checks.values()) and trial["passed"],
        "checks": checks,
        "evidence": {
            "offline_only": True,
            "network_checked": False,
            "mac_to_pi_transfer_tested": False,
            "youtube_upload_tested": False,
            "owner_review_tested": False,
            "public_release_enabled": False,
        },
        "next_action": "run_private_hardware_acceptance",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Pi acceptance report")
    parser.add_argument("--out", help="New JSON report file (never overwritten)")
    args = parser.parse_args()
    report = build_acceptance_report()
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        dest = Path(args.out)
        if dest.suffix.lower() != ".json" or dest.is_symlink():
            parser.error("output must be a new JSON file")
        with dest.open("x", encoding="utf-8") as stream:
            stream.write(output)
    else:
        print(output, end="")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
