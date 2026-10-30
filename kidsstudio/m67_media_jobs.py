"""M67 produce reproducible offline art/voice generation job packets.

Jobs describe inputs for local ComfyUI and TTS workers, but do not pretend
to generate media or grant asset QA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m67_production_plan import compile_plan


def make_jobs(storyboard):
    plan = compile_plan(storyboard)
    jobs = []
    for i, (voice, visual) in enumerate(
            zip(plan["voice_segments"], plan["visual_prompts"]), 1):
        name = f"beat_{i:02d}"
        jobs.append({
            "beat": i,
            "voice": {
                "status": "QUEUED",
                "language": voice["language"],
                "text": voice["text"],
                "duration_budget_seconds":
                    voice["end_seconds"] - voice["start_seconds"],
                "output": f"voice/{name}.wav",
                "format": "WAV_PCM_48000",
                "speaker_profile": "series_bunny_ar_iq_v1",
                "voice_rights": "REVIEW_REQUIRED",
            },
            "visual": {
                "status": "QUEUED",
                "description": visual["description"],
                "output": f"art/{name}.png",
                "canvas": [1280, 720],
                "character_reference": "KidsStudio_Bunny_reference.png",
                "style": "clean_children_2d_flat",
                "negative_constraints": [
                    "flashing lights", "crowded details", "text overlays",
                    "logos", "watermarks", "unlicensed characters",
                    "extra limbs", "distorted anatomy"
                ],
                "rights": "REVIEW_REQUIRED",
            },
            "qa": {
                "visual": "PENDING",
                "voice": "PENDING",
                "educational": "PENDING",
            },
        })
    return {
        "schema_version": 1,
        "episode_id": storyboard["episode_id"],
        "series_id": storyboard["series_id"],
        "status": "MEDIA_JOBS_PREPARED_NOT_GENERATED",
        "jobs": jobs,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--storyboard", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("output already exists")
    packet = make_jobs(json.loads(args.storyboard.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": packet["status"], "jobs": len(packet["jobs"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
