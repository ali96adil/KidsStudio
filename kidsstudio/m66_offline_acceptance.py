"""M66 one-command offline Pi master and optional reserved-journal acceptance.

No OAuth, no network, no writes to the journal, and no upload.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .m66_master_check import verify_master
from .m66_reserved_master_check import verify_reserved_master


def offline_acceptance(mp4: Path, expected_sha256: str, *,
                       journal: Path | None = None,
                       job: str | None = None) -> dict:
    if (journal is None) != (job is None):
        raise ValueError("Journal and job must be supplied together")
    master = verify_master(mp4, expected_sha256)
    if not master["pass"]:
        return {"status": "M66_OFFLINE_ACCEPTANCE_BLOCKED", "pass": False,
                "master": master, "network_used": False,
                "upload_performed": False,
                "public_release_authorized": False}
    reserved = None
    if journal is not None:
        reserved = verify_reserved_master(journal, job, mp4)
        if not reserved["pass"]:
            return {"status": "M66_OFFLINE_ACCEPTANCE_BLOCKED",
                    "pass": False, "master": master, "reserved": reserved,
                    "network_used": False, "upload_performed": False,
                    "public_release_authorized": False}
    return {"status": "M66_OFFLINE_PI_MASTER_ACCEPTED",
            "pass": True, "master": master, "reserved": reserved,
            "network_used": False, "upload_performed": False,
            "public_release_authorized": False,
            "field_youtube_upload_verified": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="kidsstudio-m66-offline-acceptance")
    parser.add_argument("--mp4", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--job")
    args = parser.parse_args(argv)
    try:
        report = offline_acceptance(
            args.mp4, args.expected_sha256, journal=args.journal, job=args.job)
    except (ValueError, OSError, sqlite3.Error):
        print("M66_OFFLINE_ACCEPTANCE_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
