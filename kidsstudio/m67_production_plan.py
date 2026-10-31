"""M67: compile approved storyboard timing into existing Godot scene spec.

Planning only: no media, voice, upload, or owner approval is generated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_episode_gate import validate_episode


MOTIONS = {
    "greeting": "wave_right",
    "teach": "neutral",
    "transfer": "head_tilt",
    "recall": "neutral",
    "reinforce": "jump",
    "close": "wave_left",
}


def compile_plan(storyboard: dict, *, fps: int = 30) -> dict:
    validate_episode(storyboard)
    if type(fps) is not int or fps not in (24, 30):
        raise ValueError("fps must be 24 or 30")
    scene = {
        "schema_version": 1,
        "fps": fps,
        "duration_seconds": storyboard["duration_seconds"],
        "beats": [
            {"start": beat["start"], "end": beat["end"],
             "motion": MOTIONS.get(beat["purpose"], "neutral")}
            for beat in storyboard["beats"]
        ],
    }
    audio = [
        {"start_seconds": beat["start"], "end_seconds": beat["end"],
         "text": beat["narration"], "language": storyboard["language"],
         "recording_status": "NOT_RECORDED"}
        for beat in storyboard["beats"]
    ]
    return {
        "schema_version": 1,
        "episode_id": storyboard["episode_id"],
        "godot_scene_spec": scene,
        "voice_segments": audio,
        "visual_prompts": [
            {"start_seconds": beat["start"], "end_seconds": beat["end"],
             "description": beat["visual"], "asset_status": "NOT_GENERATED"}
            for beat in storyboard["beats"]
        ],
        "status": "PRODUCTION_PLAN_ONLY",
        "rendered": False,
        "audio_generated": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("storyboard", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.storyboard.is_symlink() or not args.storyboard.is_file():
        p.error("regular storyboard required")
    if args.output.exists() or args.output.is_symlink():
        p.error("output already exists")
    result = compile_plan(json.loads(args.storyboard.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
