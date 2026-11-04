"""M67 batch Godot rig export/render with resumable, inspectable stage reports.

Uses existing reviewed-rig exporter and renderer. Does not approve videos,
synthesize voices, create art, transfer to Pi or contact YouTube.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .godot_export import export_godot
from .godot_render import render_godot_project
from .m67_godot_beat_export import split_beats
from .m67_production_handoff import _sha


class BatchRenderError(RuntimeError):
    pass


def batch_render(storyboard: dict, rig_manifest: Path, workspace: Path, *,
                 review_report: Path, evidence_path: Path,
                 export_fn=export_godot, render_fn=render_godot_project) -> dict:
    if workspace.exists() or workspace.is_symlink():
        raise BatchRenderError("new workspace required; never overwrite runs")
    if any((p / ".git").exists() for p in
           (workspace.resolve(), *workspace.resolve().parents)):
        raise BatchRenderError("render workspace must be outside Git")
    beats = split_beats(storyboard)
    if not rig_manifest.is_file() or rig_manifest.is_symlink():
        raise BatchRenderError("regular rig manifest required")
    if not review_report.is_file() or not evidence_path.is_file():
        raise BatchRenderError("rig review and evidence required")
    workspace.mkdir(parents=True)
    report = {
        "schema_version": 1,
        "episode_id": storyboard["episode_id"],
        "status": "RUNNING",
        "beats": [],
        "owner_review": "PENDING",
        "public_release_authorized": False,
        "youtube_upload_authorized": False,
    }
    report_path = workspace / "batch_report.json"

    def save():
        temp = workspace / "batch_report.tmp"
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        temp.replace(report_path)

    save()
    for beat in beats:
        number = beat["beat"]
        name = f"beat_{number:02d}"
        scene_path = workspace / f"{name}_scene.json"
        scene_path.write_text(json.dumps(beat["scene"], indent=2) + "\n",
                              encoding="utf-8")
        entry = {"beat": number, "scene_sha256": _sha(scene_path),
                 "status": "EXPORTING", "qa": "PENDING"}
        report["beats"].append(entry)
        save()
        try:
            project = workspace / f"{name}_project"
            rendered = workspace / f"{name}_render"
            export_fn(rig_manifest, scene_path, project, require_reviewed=True,
                      review_report=review_report, evidence_path=evidence_path)
            entry["status"] = "RENDERING"
            save()
            result = render_fn(project, rendered)
            if result.get("status") != "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW":
                raise BatchRenderError("renderer did not return a real preview")
            video = Path(result["mp4"])
            if not video.is_file() or not video.resolve().is_relative_to(workspace.resolve()):
                raise BatchRenderError("renderer output outside workspace")
            entry.update({"status": "RENDERED_PENDING_QA",
                          "video": str(video.relative_to(workspace)),
                          "sha256": _sha(video)})
            save()
        except Exception as exc:
            entry["status"] = "FAILED"
            entry["error_type"] = type(exc).__name__
            report["status"] = "BLOCKED"
            save()
            raise BatchRenderError(f"Godot batch stopped at beat {number}") from exc
    report["status"] = "ALL_BEATS_RENDERED_PENDING_QA"
    save()
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--storyboard", type=Path, required=True)
    p.add_argument("--rig", type=Path, required=True)
    p.add_argument("--review-report", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--workspace", type=Path, required=True)
    args = p.parse_args(argv)
    data = json.loads(args.storyboard.read_text(encoding="utf-8"))
    result = batch_render(data, args.rig, args.workspace,
                          review_report=args.review_report,
                          evidence_path=args.evidence)
    print(json.dumps({"status": result["status"], "beats": len(result["beats"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
