"""M67.8 generate per-beat Godot scene specifications from storyboard.

This prepares reproducible render inputs. Real rig layers and local
Godot execution remain required; no fake media or QA pass is emitted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_production_plan import compile_plan
from .godot_export import load_scene_spec


class BeatExportError(ValueError):
    pass


def split_beats(storyboard: dict) -> list[dict]:
    plan = compile_plan(storyboard)
    fps = plan["godot_scene_spec"]["fps"]
    output = []
    for index, beat in enumerate(plan["godot_scene_spec"]["beats"], 1):
        seconds = beat["end"] - beat["start"]
        if not 1 <= seconds <= 120:
            raise BeatExportError("invalid per-beat duration")
        output.append({
            "beat": index,
            "source_start_seconds": beat["start"],
            "source_end_seconds": beat["end"],
            "scene": {
                "schema_version": 1,
                "fps": fps,
                "duration_seconds": seconds,
                "beats": [{"start": 0, "end": seconds,
                           "motion": beat["motion"]}],
            },
            "render_status": "NOT_RENDERED",
            "qa_status": "PENDING",
        })
    return output


def export_beats(storyboard: dict, destination: Path) -> dict:
    if destination.exists() or destination.is_symlink():
        raise BeatExportError("destination must not exist")
    if any((parent / ".git").exists() for parent in
           (destination.resolve(), *destination.resolve().parents)):
        raise BeatExportError("render plans must stay outside Git checkout")
    beats = split_beats(storyboard)
    # Validate all Godot scene specs against the existing exporter contract
    # using a private temporary workspace, without writing media.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for item in beats:
            file = Path(tmp) / "scene.json"
            file.write_text(json.dumps(item["scene"]), encoding="utf-8")
            load_scene_spec(file)
    destination.mkdir(parents=True)
    for item in beats:
        file = destination / f"beat_{item['beat']:02d}_scene.json"
        file.write_text(json.dumps(item["scene"], indent=2) + "\n",
                        encoding="utf-8")
    report = {
        "schema_version": 1,
        "episode_id": storyboard["episode_id"],
        "status": "GODOT_BEAT_PLANS_READY_NOT_RENDERED",
        "beats": [{"beat": item["beat"],
                   "source_start_seconds": item["source_start_seconds"],
                   "source_end_seconds": item["source_end_seconds"],
                   "scene_file": f"beat_{item['beat']:02d}_scene.json",
                   "render_status": item["render_status"],
                   "qa_status": item["qa_status"]}
                  for item in beats],
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
    (destination / "beat_export_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--storyboard", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args(argv)
    if args.storyboard.is_symlink() or not args.storyboard.is_file():
        p.error("regular storyboard required")
    result = export_beats(
        json.loads(args.storyboard.read_text(encoding="utf-8")),
        args.output_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
