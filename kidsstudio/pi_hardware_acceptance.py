"""Offline, evidence-based Mac -> Pi -> private YouTube acceptance gate.

This tool never accesses credentials, the network or YouTube.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import stat
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
    if (not isinstance(data, dict) or data.get("version") != 1 or
            set(data) != {"version", "steps"}):
        raise ValueError("expected version 1 acceptance evidence with no extra fields")
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
        "remaining_steps": [name for name in REQUIRED_STEPS if statuses[name] != "pass"],
        "next_step": next((name for name in REQUIRED_STEPS if statuses[name] != "pass"), None),
        "youtube_public_release_authorized": False,
        "network_checked": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--init", type=Path, help="create new private not-tested evidence file")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--step", choices=REQUIRED_STEPS)
    parser.add_argument("--status", choices=sorted(_ALLOWED))
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
    try:
        fd = os.open(args.evidence, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError("evidence must not be a symlink") from exc
        raise
    with os.fdopen(fd, "rb") as stream:
        evidence_stat = os.fstat(stream.fileno())
        if not stat.S_ISREG(evidence_stat.st_mode):
            raise ValueError("evidence must be a regular file")
        if stat.S_IMODE(evidence_stat.st_mode) & 0o077 or evidence_stat.st_size > 16384:
            raise ValueError("evidence file must be private and at most 16 KiB")
        raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError("evidence exceeds 16 KiB")
        evidence = json.loads(raw.decode("utf-8"))
    if (args.step is None) != (args.status is None):
        parser.error("--step and --status must be used together")
    if args.step is not None:
        if args.out is not None:
            parser.error("--out cannot be used with --step")
        evaluate_evidence(evidence)
        evidence["steps"][args.step] = args.status
        # Write a new file, fsync, then atomically replace the original.
        # No free-form notes or URLs are accepted by this command.
        import tempfile
        fd, temporary = tempfile.mkstemp(prefix=".acceptance-", dir=args.evidence.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(evidence, stream, indent=2)
                stream.write(chr(10))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, args.evidence)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return 0
    report = evaluate_evidence(evidence)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
    else:
        print(output, end="")
    return 0 if report["ready_for_live_operation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
