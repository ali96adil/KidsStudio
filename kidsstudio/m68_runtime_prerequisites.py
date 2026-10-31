"""Read-only Mac/Pi runtime prerequisites for M68 integration.

Never starts model inference, connects to YouTube, or transfers media.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def assess(role, *, db=None, media=None, require_ollama=False):
    if role not in ("mac", "pi"):
        raise ValueError("role must be mac or pi")
    checks = {}
    for binary in ("python3", "ffmpeg", "ffprobe", "ssh", "scp"):
        checks[binary] = bool(shutil.which(binary))
    if role == "mac":
        checks["godot"] = bool(shutil.which("godot"))
        checks["ollama"] = bool(shutil.which("ollama"))
        checks["local_ai_runtime_configured"] = (
            checks["ollama"] if require_ollama else None)
    else:
        checks["sqlite_database_present"] = (
            isinstance(db, (str, Path)) and Path(db).is_file())
        checks["private_staged_media_present"] = (
            isinstance(media, (str, Path)) and Path(media).is_file())
    required = ["python3", "ffmpeg", "ffprobe"]
    if role == "mac":
        required += ["godot"]
        if require_ollama:
            required += ["ollama"]
    else:
        required += ["sqlite_database_present", "private_staged_media_present"]
    missing = [name for name in required if checks[name] is not True]
    return {
        "role": role, "status": "PREREQUISITES_PRESENT_NOT_END_TO_END_TESTED"
        if not missing else "BLOCKED_MISSING_PREREQUISITES",
        "checks": checks, "missing": missing,
        "real_model_inference_verified": False,
        "mac_pi_transfer_verified": False,
        "youtube_private_upload_verified": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("mac", "pi"), required=True)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--media", type=Path)
    parser.add_argument("--require-ollama", action="store_true")
    args = parser.parse_args(argv)
    report = assess(args.role, db=args.db, media=args.media,
                    require_ollama=args.require_ollama)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not report["missing"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
