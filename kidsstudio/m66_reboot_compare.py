"""M66 compare two read-only Pi upload journal reports across a reboot.

This tool does not touch the SQLite journal, YouTube, or Pi. The operator
captures two JSON reports before/after a restart and compares their durable
states. It fails closed on unexpected changes, missing jobs, or unknown state.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

STATES = ("STARTED", "UPLOADED_UNVERIFIED", "PRIVATE_VERIFIED")


def compare(before: dict, after: dict) -> dict:
    for report in (before, after):
        if not isinstance(report, dict) or report.get("status") != "M66_READ_ONLY_JOURNAL_REPORT":
            raise ValueError("Invalid M66 journal report")
        if report.get("network_used") is not False or report.get("database_modified") is not False:
            raise ValueError("Report must be read-only")
        digest = report.get("snapshot_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Missing or malformed full-journal snapshot")
        counts = report.get("states")
        if not isinstance(counts, dict) or set(counts) != set(STATES):
            raise ValueError("Invalid state counts")
        if any(type(counts[s]) is not int or counts[s] < 0 for s in STATES):
            raise ValueError("Invalid state count")
        if type(report.get("total")) is not int or report["total"] != sum(counts.values()):
            raise ValueError("Inconsistent total")
        unresolved = report.get("requires_manual_reconciliation")
        if not isinstance(unresolved, list) or any(not isinstance(x, str) or not x for x in unresolved):
            raise ValueError("Invalid reconciliation list")
        if len(unresolved) != len(set(unresolved)):
            raise ValueError("Duplicate reconciliation jobs")
        if len(unresolved) != counts["STARTED"] + counts["UPLOADED_UNVERIFIED"]:
            raise ValueError("Reconciliation count mismatch")
    # Exact state counts and unresolved identities must remain stable across
    # a quiescent reboot. This is deliberately conservative: any background
    # upload activity between snapshots requires manual review.
    stable = (before["snapshot_sha256"] == after["snapshot_sha256"] and
              before["states"] == after["states"] and
              before["total"] == after["total"] and
              before["requires_manual_reconciliation"] == after["requires_manual_reconciliation"])
    return {
        "status": "M66_REBOOT_JOURNAL_STABLE" if stable else "M66_REBOOT_JOURNAL_CHANGED_REVIEW_REQUIRED",
        "pass": stable,
        "network_used": False,
        "public_release_authorized": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kidsstudio-m66-reboot-compare")
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
        result = compare(before, after)
    except (OSError, ValueError, TypeError, KeyError):
        print("M66_REBOOT_COMPARE_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
