"""M66 offline evidence bundle: combine independent checks, never certify field upload.

Reads existing JSON receipts only. Does not probe hardware, access the
network, write SQLite, or authorize any YouTube action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def summarize(acceptance: dict, before: dict, after: dict) -> dict:
    from .m66_reboot_compare import compare
    if not isinstance(acceptance, dict):
        raise ValueError("Missing offline acceptance receipt")
    if (acceptance.get("status") != "M66_OFFLINE_PI_MASTER_ACCEPTED"
        or acceptance.get("pass") is not True
        or acceptance.get("network_used") is not False
        or acceptance.get("upload_performed") is not False
        or acceptance.get("public_release_authorized") is not False
        or acceptance.get("field_youtube_upload_verified") is not False):
        raise ValueError("Invalid offline acceptance receipt")
    master = acceptance.get("master")
    if (not isinstance(master, dict)
        or master.get("status") != "M66_PI_MASTER_SHA256_MATCH"
        or master.get("pass") is not True
        or master.get("expected_sha256") != master.get("actual_sha256")):
        raise ValueError("Invalid master integrity proof")
    reserved = acceptance.get("reserved")
    if reserved is not None and (
        not isinstance(reserved, dict)
        or reserved.get("status") != "M66_RESERVED_PI_MASTER_MATCH"
        or reserved.get("pass") is not True
        or reserved.get("network_used") is not False
        or reserved.get("upload_performed") is not False):
        raise ValueError("Invalid journal reservation proof")
    if reserved is not None:
        if (reserved.get("master_sha256") != master.get("actual_sha256")
            or reserved.get("size_bytes") != master.get("size_bytes")
            or not isinstance(reserved.get("render_job_id"), str)
            or len(reserved["render_job_id"]) != 32):
            raise ValueError("Reservation does not match master receipt")
    reboot = compare(before, after)
    stable = reboot["pass"]
    unresolved = before["requires_manual_reconciliation"]
    clean = stable and not unresolved
    return {
        "status": ("M66_OFFLINE_EVIDENCE_COMPLETE_FIELD_PENDING"
                   if clean else "M66_OFFLINE_EVIDENCE_BLOCKED"),
        "pass": clean,
        "checks": {
            "master_sha256": True,
            "reserved_journal_checked": reserved is not None,
            "upload_attempt_linked_to_master": reserved is not None,
            "journal_reboot_stable": stable,
            "journal_unresolved_uploads_clear": not bool(unresolved),
            "physical_pi_verified": False,
            "mac_off_pi_only_upload_verified": False,
            "youtube_private_verified": False,
            "owner_review_verified": False,
        },
        "journal_requires_manual_reconciliation":
            unresolved,
        "network_used": False,
        "upload_performed": False,
        "public_release_authorized": False,
        "field_qualified": False,
        "evidence_scope": "OFFLINE_ONLY_NOT_PI_OR_YOUTUBE_FIELD_PROOF",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="kidsstudio-m66-evidence-summary")
    p.add_argument("--acceptance", type=Path, required=True)
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--after", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        receipts = [json.loads(x.read_text(encoding="utf-8"))
                    for x in (args.acceptance, args.before, args.after)]
        report = summarize(*receipts)
    except (OSError, ValueError, TypeError, KeyError):
        print("M66_EVIDENCE_SUMMARY_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
