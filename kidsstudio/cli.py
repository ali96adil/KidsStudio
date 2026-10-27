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
from .godot_export import GodotExportError, export_godot
from .godot_render import GodotRenderError, render_godot_project
from .reviewer import VisionReviewError, review_rig
from .cycle import CycleError, run_character_cycle


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
    comfy.add_argument("--reference-name", help="Already uploaded local ComfyUI reference PNG filename")
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
    factory.add_argument("--reference", help="Canonical local PNG to upload into approved reference-conditioned workflow")
    factory.add_argument("--review-model",
                         help="Optional installed local multimodal Ollama model for independent QA")
    factory.add_argument("--execute", action="store_true",
                         help="Required: queue all part-generation jobs in local ComfyUI")
    motion = commands.add_parser("motion-preview", help="Render visual evidence for a separated rig")
    motion.add_argument("manifest")
    motion.add_argument("--out", required=True)
    motion.add_argument("--preview-side", type=int, default=384)
    review = commands.add_parser("visual-review", help="Independent local AI review of rendered rig evidence")
    review.add_argument("manifest")
    review.add_argument("--evidence", required=True)
    review.add_argument("--model", required=True)
    review.add_argument("--out", required=True)
    review.add_argument("--reference",
                        help="Optional local canonical character reference image")
    review.add_argument("--execute", action="store_true",
                        help="Required: send contact sheet to installed local vision model")
    godot = commands.add_parser("export-godot", help="Export a standalone Godot 4 project from rig and scene JSON")
    godot.add_argument("manifest")
    godot.add_argument("--scene", required=True)
    godot.add_argument("--out", required=True)
    godot.add_argument("--require-reviewed", action="store_true",
                       help="Demand a fresh local independent AI PASS before export")
    godot.add_argument("--review-report")
    godot.add_argument("--evidence")
    render = commands.add_parser("render-godot", help="Render verified exported Godot project to local H.264 MP4")
    render.add_argument("project")
    render.add_argument("--out", required=True)
    render.add_argument("--godot", default="godot")
    render.add_argument("--ffmpeg", default="ffmpeg")
    render.add_argument("--timeout", type=int, default=1800)
    cycle = commands.add_parser(
        "produce-character", help="Bounded rig-first batch, AI review and targeted repair"
    )
    cycle.add_argument("blueprint")
    cycle.add_argument("--workflow", required=True)
    cycle.add_argument("--profile", required=True)
    cycle.add_argument("--reference", required=True)
    cycle.add_argument("--review-model", required=True)
    cycle.add_argument("--out", required=True)
    cycle.add_argument("--max-attempts", type=int, default=2)
    cycle.add_argument("--max-repair-parts", type=int, default=3)
    cycle.add_argument("--timeout", type=int, default=900)
    cycle.add_argument("--preview-side", type=int, default=384)
    cycle.add_argument("--execute", action="store_true",
                       help="Required: invoke preapproved local ComfyUI and vision model")
    args = parser.parse_args(argv)

    try:
        if args.command == "produce-character":
            if not args.execute:
                print("ERROR: Explicit --execute required for local production cycle.",
                      file=sys.stderr)
                return 2
            result = run_character_cycle(
                args.blueprint, args.workflow, args.profile,
                args.reference, args.out,
                vision_model=args.review_model,
                max_attempts=args.max_attempts,
                max_repair_parts=args.max_repair_parts,
                timeout_seconds=args.timeout,
                preview_side=args.preview_side,
            )
            print(json.dumps({
                "status": result["status"],
                "attempts": len(result["attempts"]),
                "generated_comfy_jobs": sum(
                    i["generated_comfy_jobs"] for i in result["attempts"]
                ),
                "report": str(Path(args.out).resolve() / "production_cycle.json"),
                "owner_publication_approval_required": True,
            }, indent=2, ensure_ascii=False))
            return 0 if result["status"] == (
                "INTERNAL_ASSET_APPROVED_NOT_FOR_PUBLICATION") else 1
        if args.command == "comfy-prepare":
            prepared = prepare_submission(
                args.workflow, args.profile,
                prompt_text=args.prompt, filename_prefix=args.prefix,
                reference_image_name=args.reference_name,
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
        if args.command == "render-godot":
            result = render_godot_project(
                args.project, args.out,
                godot_executable=args.godot,
                ffmpeg_executable=args.ffmpeg,
                timeout_seconds=args.timeout,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.command == "export-godot":
            result = export_godot(
                args.manifest, args.scene, args.out,
                require_reviewed=args.require_reviewed,
                review_report=args.review_report,
                evidence_path=args.evidence,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        if args.command == "visual-review":
            if not args.execute:
                print("ERROR: Explicit --execute required to run local visual reviewer.", file=sys.stderr)
                return 2
            result = review_rig(
                args.manifest, args.evidence, args.out,
                model=args.model, reference_file=args.reference,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["verdict"] == "PASS" else 1
        if args.command == "build-character":
            if not args.execute:
                print("ERROR: Explicit --execute required for actual ComfyUI generation.", file=sys.stderr)
                return 2
            result = build_character(
                args.blueprint, args.workflow, args.profile, args.out,
                timeout_seconds=args.timeout, preview_side=args.preview_side,
                review_model=args.review_model,
                reference_image=args.reference,
            )
            print(json.dumps({
                "status": result["status"], "character_id": result["character_id"],
                "part_jobs": len(result["jobs"]), "technical_pass": result["technical_pass"],
                "visual_review_required": result["visual_review_required"],
                "visual_review_status": result.get("visual_review", {}).get("status", "NOT_RUN"),
                "report": str(Path(args.out).resolve() / "factory_report.json"),
            }, indent=2))
            if args.review_model:
                return 0 if result["status"] == "APPROVED_BY_LOCAL_AI_QA" else 1
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
    except (OSError, ValueError, TypeError, KeyError, ComfySafetyError, FactoryError, TimeoutError, VisionReviewError, GodotExportError, GodotRenderError, CycleError) as exc:
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
