"""Run an exported KidsStudio Godot project and encode an MP4 locally.

No shell execution, implicit network dependency, cloud upload or publishing.
Rendering does not constitute independent review of the resulting video.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .godot_export import GodotExportError, load_scene_spec


class GodotRenderError(RuntimeError):
    """The project is unverified or local rendering failed."""


def _hash(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def _write_status(file: Path, status: dict[str, Any]) -> None:
    temp = file.with_suffix(".tmp")
    temp.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    temp.replace(file)


def render_godot_project(
    project_directory: str | Path,
    output_directory: str | Path,
    *,
    godot_executable: str = "godot",
    ffmpeg_executable: str = "ffmpeg",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    project = Path(project_directory).expanduser().resolve()
    out = Path(output_directory).expanduser().resolve()
    if out.exists():
        raise FileExistsError("Movie output already exists; preserve previous render.")
    if any((p / ".git").exists() for p in (out, *out.parents)):
        raise GodotRenderError("Rendered media must be stored outside Git.")
    if not 30 <= timeout_seconds <= 7200:
        raise GodotRenderError("timeout_seconds must be between 30 and 7200.")
    if not project.is_dir():
        raise GodotRenderError("Godot project directory does not exist.")

    try:
        info = json.loads((project / "export_report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GodotRenderError(f"Missing KidsStudio exporter metadata: {exc}") from exc
    if info.get("status") not in (
        "PREVIEW_ONLY_UNAPPROVED",
        "INTERNAL_RIG_QA_PASSED_NOT_PUBLICATION_APPROVED",
    ):
        raise GodotRenderError("This is not a recognized KidsStudio rig export.")
    expected_files = info.get("project_hashes")
    if not isinstance(expected_files, dict) or not expected_files:
        raise GodotRenderError("Missing project-integrity hashes; export with updated KidsStudio.")
    for name, digest in expected_files.items():
        if (not isinstance(name, str) or name.startswith("/")
                or "\\" in name or ".." in Path(name).parts
                or not isinstance(digest, str) or len(digest) != 64):
            raise GodotRenderError("Invalid project integrity record.")
        path = (project / name).resolve()
        if not path.is_relative_to(project) or not path.is_file():
            raise GodotRenderError(f"Project file missing or escapes export: {name}")
        if _hash(path) != digest:
            raise GodotRenderError(f"Exported file changed after approval: {name}")

    player = project / "scripts" / "rig_player.gd"
    canonical = Path(__file__).with_name("godot_player.gd")
    if _hash(player) != _hash(canonical):
        raise GodotRenderError("Executable GDScript differs from audited KidsStudio player.")
    scene = load_scene_spec(project / "scene_spec.json")
    fps = scene["fps"]
    frames = round(fps * scene["duration_seconds"])
    if not 1 <= frames <= 18000:
        raise GodotRenderError("Render exceeds 18000-frame safety limit.")

    godot = shutil.which(godot_executable)
    ffmpeg = shutil.which(ffmpeg_executable)
    if not godot or not ffmpeg:
        raise GodotRenderError("Installed local Godot 4 and FFmpeg are required.")

    out.mkdir(parents=True, exist_ok=False)
    avi = out / "godot_preview.avi"
    mp4 = out / "character_preview.mp4"
    status_file = out / "render_report.json"
    status: dict[str, Any] = {
        "schema_version": 1,
        "status": "RENDERING",
        "source_project": str(project),
        "source_asset_gate": info["status"],
        "fps": fps,
        "duration_seconds": scene["duration_seconds"],
        "frames_expected": frames,
        "owner_publication_approval_required": True,
    }
    _write_status(status_file, status)
    try:
        # A true movie with ImageTexture sprites must use a real renderer.
        # Godot's --headless dummy texture storage may crash when movie capture
        # requests painted textures. Linux CI runs this under Xvfb/Mesa instead.
        completed = subprocess.run([
            godot, "--path", str(project),
            "--rendering-method", "gl_compatibility",
            "--write-movie", str(avi),
            "--fixed-fps", str(fps),
            "--quit-after", str(frames),
        ], check=True, capture_output=True, text=True,
           timeout=timeout_seconds)
        output_log = ((getattr(completed, "stdout", "") or "") + "\\n" +
                      (getattr(completed, "stderr", "") or ""))
        if "SCRIPT ERROR:" in output_log or "ERROR:" in output_log:
            raise GodotRenderError(
                "Godot reported a script or rendering error: " +
                output_log[-1600:]
            )
        if not avi.is_file() or avi.stat().st_size == 0:
            raise GodotRenderError("Godot completed without writing AVI frames.")
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-i", str(avi), "-c:v", "libx264", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(mp4),
        ], check=True, capture_output=True, text=True,
           timeout=timeout_seconds)
        if not mp4.is_file() or mp4.stat().st_size == 0:
            raise GodotRenderError("FFmpeg completed without generating MP4.")
        status.update({
            "status": "VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW",
            "mp4": str(mp4),
            "mp4_sha256": _hash(mp4),
            "mp4_bytes": mp4.stat().st_size,
            "godot_movie": str(avi),
            "godot_movie_sha256": _hash(avi),
        })
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError,
            GodotRenderError) as exc:
        status["status"] = "RENDER_FAILED"
        status["error_type"] = type(exc).__name__
        status["error"] = str(exc)[:2000]
        std_err = getattr(exc, "stderr", None) or ""
        std_out = getattr(exc, "stdout", None) or ""
        if isinstance(std_err, bytes):
            std_err = std_err.decode("utf-8", errors="replace")
        if isinstance(std_out, bytes):
            std_out = std_out.decode("utf-8", errors="replace")
        diagnostic = (str(std_out) + "\\n" + str(std_err))[-6000:]
        status["renderer_log_tail"] = diagnostic
        _write_status(status_file, status)
        raise GodotRenderError(
            f"Local renderer failed. Inspect {status_file}. "
            f"Renderer output: {diagnostic[-2000:]}"
        ) from exc
    _write_status(status_file, status)
    return status
