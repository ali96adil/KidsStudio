"""Command-line interface for safe rig planning and deterministic QA."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .planner import make_rig_plan
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
    args = parser.parse_args(argv)

    try:
        if args.command == "plan-rig":
            result = make_rig_plan(args.blueprint)
            success = True
        else:
            result = check_rig(args.manifest)
            success = bool(result["passed"])
    except (OSError, ValueError, TypeError, KeyError) as exc:
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
