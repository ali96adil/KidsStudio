"""M67 single read-only Mac/Pi production status report.

Consumes existing JSON receipts and does not change workflow states.
A report cannot authorize private upload or public publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


STAGES = (
    ("jobs", "jobs.json"),
    ("images", "comfy_batch_report.json"),
    ("voice", "voice_batch_report.json"),
    ("structural", "media_inspection.json"),
    ("decode", "media_decode_report.json"),
    ("review", "reviewed_manifest.json"),
    ("godot", "godot/batch_report.json"),
    ("master", "master_inventory.json"),
    ("transfer", "pi_transfer_report.json"),
)


def summarize(root):
    root = Path(root)
    steps = []
    for stage, name in STAGES:
        path = root / name
        if not path.is_file() or path.is_symlink():
            steps.append({"stage": stage, "status": "NOT_RECORDED"})
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            state = doc.get("status", "UNKNOWN")
            if not isinstance(state, str):
                state = "INVALID"
        except (ValueError, OSError):
            state = "UNREADABLE"
        steps.append({"stage": stage, "status": state})
    return {
        "status": "M67_PRODUCTION_STATUS_READ_ONLY",
        "steps": steps,
        "pi_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    args = p.parse_args(argv)
    print(json.dumps(summarize(args.root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
