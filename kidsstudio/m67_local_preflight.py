"""M67 operational readiness gate for local production.

Runs only checks. Never approves, transfers, publishes, or modifies assets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from .m67_episode_gate import validate_episode
from .m67_production_handoff import audit_assets
from .m67_batch_inspection import inspect_batch


def preflight(storyboard, manifest, root, *, batch=None, workspace=None):
    checks = {}
    try:
        validate_episode(storyboard)
        checks["storyboard"] = "PASS"
    except (ValueError, KeyError, TypeError) as exc:
        checks["storyboard"] = type(exc).__name__
    checks["godot"] = "AVAILABLE" if shutil.which("godot") else "MISSING"
    checks["ffmpeg"] = "AVAILABLE" if shutil.which("ffmpeg") else "MISSING"
    checks["ffprobe"] = "AVAILABLE" if shutil.which("ffprobe") else "MISSING"
    try:
        result = audit_assets(manifest, Path(root))
        checks["assets"] = "PASS" if result["render_authorized"] else "BLOCKED"
    except (ValueError, OSError, KeyError, TypeError) as exc:
        checks["assets"] = type(exc).__name__
    if batch is None:
        checks["godot_batch"] = "NOT_PROVIDED"
    else:
        result = inspect_batch(manifest, batch, Path(root), Path(workspace))
        checks["godot_batch"] = result["status"]
    ready = all(checks[key] == "PASS" for key in ("storyboard", "assets"))
    ready = ready and all(checks[key] == "AVAILABLE"
                          for key in ("godot", "ffmpeg", "ffprobe"))
    return {
        "status": "LOCAL_PRODUCTION_INPUTS_READY" if ready else "BLOCKED",
        "checks": checks,
        "godot_batch_ready": checks["godot_batch"] == "RENDERS_VERIFIED_PENDING_QA",
        "pi_transfer_authorized": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--batch-report", type=Path)
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    if args.batch_report and not args.workspace:
        parser.error("--workspace required with --batch-report")
    report = preflight(
        json.loads(args.storyboard.read_text(encoding="utf-8")),
        json.loads(args.manifest.read_text(encoding="utf-8")),
        args.root,
        batch=json.loads(args.batch_report.read_text(encoding="utf-8"))
        if args.batch_report else None,
        workspace=args.workspace)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "LOCAL_PRODUCTION_INPUTS_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
