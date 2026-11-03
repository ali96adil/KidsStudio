"""Offline, evidence-based Mac -> Pi -> private YouTube acceptance gate.

This tool never accesses credentials, the network or YouTube.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

REQUIRED_STEPS = (
    "mac_video_export",
    "mac_to_pi_transfer",
    "pi_media_integrity",
    "pi_private_upload",
    "youtube_private_visibility",
    "iphone_owner_review",
    "owner_notes_recorded",
)
_ALLOWED = {"pass", "fail", "not_tested"}


def evaluate_evidence(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("expected version 1 acceptance evidence")
    steps = data.get("steps")
    if not isinstance(steps, dict) or set(steps) != set(REQUIRED_STEPS):
        raise ValueError("all required acceptance steps must be present")
    statuses = {}
    for name in REQUIRED_STEPS:
        value = steps[name]
        if not isinstance(value, str) or value not in _ALLOWED:
            raise ValueError("invalid acceptance step status")
        statuses[name] = value
    return {
        "version": 1,
        "ready_for_live_operation": all(v == "pass" for v in statuses.values()),
        "passed": sum(v == "pass" for v in statuses.values()),
        "failed": sum(v == "fail" for v in statuses.values()),
        "not_tested": sum(v == "not_tested" for v in statuses.values()),
        "steps": statuses,
        "youtube_public_release_authorized": False,
        "network_checked": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--init", type=Path, help="create new private not-tested evidence file")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.init is not None:
        if args.evidence is not None or args.out is not None:
            parser.error("--init cannot be combined with --evidence or --out")
        data = {"version": 1, "steps": {name: "not_tested" for name in REQUIRED_STEPS}}
        fd = os.open(args.init, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write(chr(10))
            stream.flush()
            os.fsync(stream.fileno())
        return 0
    if args.evidence is None:
        parser.error("--evidence is required unless --init is used")
    report = evaluate_evidence(json.loads(args.evidence.read_text(encoding="utf-8")))
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with args.out.open("x", encoding="utf-8") as stream:
            stream.write(output)
    else:
        print(output, end="")
    return 0 if report["ready_for_live_operation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
