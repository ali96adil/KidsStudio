"""Command-line interface for safe rig planning and deterministic QA."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .planner import make_rig_plan
from .comfy import ComfySafetyError, prepare_submission, queue_on_local_comfy
from .rigqa import check_rig
from .factory import build_character, FactoryError
from .motion import create_motion_evidence


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
    factory = commands.add_parser("build-character", help="Generate rig-first parts with local ComfyUI")
    factory.add_argument("blueprint")
    factory.add_argument("--workflow", required=True)
    factory.add_argument("--profile", required=True)
    factory.add_argument("--out", required=True)
    factory.add_argument("--timeout", type=int, default=900)
    factory.add_argument("--preview-side", type=int, default=384)
    factory.add_argument("--execute", action="store_true",
                         help="Required: queue all part-generation jobs in local ComfyUI")
    motion = commands.add_parser("motion-preview", help="Render visual evidence for a separated rig")
    motion.add_argument("manifest")
    motion.add_argument("--out", required=True)
    motion.add_argument("--preview-side", type=int, default=384)
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
        if args.command == "build-character":
            if not args.execute:
                print("ERROR: Explicit --execute required for actual ComfyUI generation.", file=sys.stderr)
                return 2
            result = build_character(
                args.blueprint, args.workflow, args.profile, args.out,
                timeout_seconds=args.timeout, preview_side=args.preview_side,
            )
            print(json.dumps({
                "status": result["status"], "character_id": result["character_id"],
                "part_jobs": len(result["jobs"]), "technical_pass": result["technical_pass"],
                "visual_review_required": result["visual_review_required"],
                "report": str(Path(args.out).resolve() / "factory_report.json"),
            }, indent=2))
            return 0 if result["technical_pass"] else 1
        if args.command == "motion-preview":
            result = create_motion_evidence(
                args.manifest, args.out, side=args.preview_side
            )
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "plan-rig":
            result = make_rig_plan(args.blueprint)
            success = True
        else:
            result = check_rig(args.manifest)
            success = bool(result["passed"])
    except (OSError, ValueError, TypeError, KeyError, ComfySafetyError, FactoryError, TimeoutError) as exc:
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
