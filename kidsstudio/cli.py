"""Command-line interface for safe rig planning and deterministic QA."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .planner import make_rig_plan
from .comfy import ComfySafetyError, prepare_submission, queue_on_local_comfy
from .rigqa import check_rig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kidsstudio")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan-rig", help="Make generation instructions from a blueprint")
    plan.add_argument("blueprint")
    plan.add_argument("--output", type=Path)
    check = commands.add_parser("qa-rig", help="Check separate rig assets; not final visual QA")
    check.add_argument("manifest")
    check.add_argument("--report", type=Path)
    comfy = commands.add_parser("comfy-prepare", help="Safely prepare an approved local ComfyUI API workflow")
    comfy.add_argument("workflow")
    comfy.add_argument("--profile", required=True)
    comfy.add_argument("--prompt", required=True)
    comfy.add_argument("--prefix", required=True)
    comfy.add_argument("--base-url", default="http://127.0.0.1:8188")
    comfy.add_argument("--submit", action="store_true",
                       help="Explicitly queue a validated job on local ComfyUI")
    args = parser.parse_args(argv)

    try:
        if args.command == "comfy-prepare":
            prepared = prepare_submission(
                args.workflow, args.profile,
                prompt_text=args.prompt, filename_prefix=args.prefix
            )
            # Avoid dumping full prompts/workflows to logs.
            result = (
                queue_on_local_comfy(prepared, base_url=args.base_url)
                if args.submit else
                {"status": prepared["status"], "workflow_sha256": prepared["workflow_sha256"],
                 "node_count": prepared["node_count"], "models": prepared["models"]}
            )
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "plan-rig":
            result = make_rig_plan(args.blueprint)
            success = True
        else:
            result = check_rig(args.manifest)
            success = bool(result["passed"])
    except (OSError, ValueError, TypeError, KeyError, ComfySafetyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output if args.command == "plan-rig" else args.report:
        target = args.output if args.command == "plan-rig" else args.report
        assert target is not None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        print(f"Saved: {target}")
    else:
        print(output)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
