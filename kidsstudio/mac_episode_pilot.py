"""One foreground Mac command: verified Godot pilot render + Arabic WAV mux.

Defaults to local read-only preflight. With --execute-render it performs local
Godot/FFmpeg only. No model, paid API, SSH, YouTube, or publishing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .audio_pcm_energy import AudioPresenceError, check_pcm_timeline_energy
from .godot_export import GodotExportError, load_scene_spec
from .godot_render import GodotRenderError, render_godot_project
from .mac_episode_audio import (
    EpisodeMuxError, _private_root, _wav_duration, mux_episode_pilot,
)
from .optional_tool_evidence import ToolEvidenceError, private_evidence_file
from .transfer_verify import verify_staged_file

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,158}\.mp4\Z")
_SHA = re.compile(r"[a-fA-F0-9]{64}\Z")


def run_mac_episode_pilot(
    *, godot_project: str, narration_root: str,
    narration_name: str, narration_sha256: str, output_root: str,
    output_name: str = "colors_ar_01.mp4", execute: bool = False,
) -> dict:
    if type(execute) is not bool:
        raise EpisodeMuxError("Execute must be explicit boolean.")
    if not isinstance(output_name, str) or not _NAME.fullmatch(output_name):
        raise EpisodeMuxError("Invalid pilot MP4 basename.")
    if not isinstance(narration_sha256, str) or not _SHA.fullmatch(narration_sha256):
        raise EpisodeMuxError("Trusted narration SHA256 required.")
    output = _private_root(output_root)
    project = Path(godot_project).expanduser().resolve(strict=True)
    if not project.is_dir():
        raise EpisodeMuxError("Existing exported Godot project required.")
    if any((part / ".git").exists() for part in (project, *project.parents)):
        raise EpisodeMuxError("Godot export must be outside Git checkout.")
    report_file = project / "export_report.json"
    if not report_file.is_file() or report_file.stat().st_size > 65536:
        raise EpisodeMuxError("Missing bounded Godot export report.")
    try:
        export = json.loads(report_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EpisodeMuxError("Invalid Godot export report.") from exc
    if not isinstance(export, dict) or export.get("status") not in (
        "PREVIEW_ONLY_UNAPPROVED",
        "INTERNAL_RIG_QA_PASSED_NOT_PUBLICATION_APPROVED",
    ):
        raise EpisodeMuxError("Unrecognized Godot preview export.")
    scene = load_scene_spec(project / "scene_spec.json")
    # The Godot renderer validates source-file hashes before executing.
    file = private_evidence_file(
        narration_root, narration_name, max_bytes=1024**3)
    if not narration_name.endswith(".wav"):
        raise EpisodeMuxError("Expected original 16-bit PCM narration WAV.")
    check = verify_staged_file(
        root=narration_root, relative_path=narration_name,
        expected_sha256=narration_sha256, max_bytes=1024**3)
    if check["status"] != "VERIFIED":
        raise EpisodeMuxError("Narration SHA256 mismatch.")
    voice_sec = _wav_duration(file)
    scene_sec = scene["duration_seconds"]
    if abs(voice_sec - scene_sec) > 0.75:
        raise EpisodeMuxError("Narration does not fit the scene duration.")
    render_dir = output / (output_name.removesuffix(".mp4") + "-godot-render")
    finished = output / output_name
    if render_dir.exists() or render_dir.is_symlink() or finished.exists() or finished.is_symlink():
        raise FileExistsError("Pilot render or output exists; never overwrite.")
    preliminary = {
        "schema_version": 1,
        "status": "MAC_PILOT_READY_TO_RENDER" if not execute else "MAC_PILOT_RENDER_UNVERIFIED",
        "episode_video_name": output_name,
        "narration_sha256": narration_sha256.lower(),
        "scene_seconds": scene_sec,
        "narration_seconds": round(voice_sec, 3),
        "render_executed": False,
        "narration_mixed": False,
        "rights_and_educational_review_required": True,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }
    if not execute:
        return preliminary
    try:
        check_pcm_timeline_energy(
            root=narration_root, relative_path=narration_name,
            beat_durations=[beat["end"] - beat["start"]
                            for beat in scene["beats"]])
    except (AudioPresenceError, OSError, ValueError) as exc:
        raise EpisodeMuxError(
            "Narration is missing energy in a story beat.") from exc
    native = render_godot_project(project, render_dir)
    if native.get("status") != "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW":
        raise EpisodeMuxError("Godot render did not complete its private preview.")
    result = mux_episode_pilot(
        video_root=str(render_dir), video_name="character_preview.mp4",
        video_sha256=native["mp4_sha256"],
        narration_root=narration_root, narration_name=narration_name,
        narration_sha256=narration_sha256,
        output_root=str(output), output_name=output_name,
        execute=True,
    )
    if result.get("status") != "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED":
        raise EpisodeMuxError("Audio/video finalization failed.")
    preliminary.update({
        "status": "MAC_PILOT_FINAL_MP4_PRIVATE_UNREVIEWED",
        "render_executed": True,
        "narration_mixed": True,
        "final_mp4_sha256": result["final_mp4_sha256"],
        "final_mp4_bytes": result["final_mp4_bytes"],
        "native_render_sha256": native["mp4_sha256"],
    })
    return preliminary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-shot Mac Godot pilot and owner-supplied original Arabic WAV")
    parser.add_argument("--godot-project", required=True)
    parser.add_argument("--narration-root", required=True)
    parser.add_argument("--narration-name", required=True)
    parser.add_argument("--narration-sha256", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--output-name", default="colors_ar_01.mp4")
    parser.add_argument("--execute-render", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_mac_episode_pilot(
            godot_project=args.godot_project,
            narration_root=args.narration_root,
            narration_name=args.narration_name,
            narration_sha256=args.narration_sha256,
            output_root=args.output_root,
            output_name=args.output_name,
            execute=args.execute_render,
        )
    except (EpisodeMuxError, ToolEvidenceError, GodotExportError,
            GodotRenderError, OSError, ValueError, KeyError, TypeError):
        print(json.dumps({
            "status": "MAC_PILOT_BLOCKED_OR_UNVERIFIED",
            "pi_transfer_performed": False,
            "youtube_upload_performed": False,
            "publication_approved": False,
        }))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "MAC_PILOT_FINAL_MP4_PRIVATE_UNREVIEWED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
