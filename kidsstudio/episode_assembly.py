"""Offline-first, pinned KidsStudio episode assembler (not a model runner).

Combines *already generated* local Chatterbox/LTX A2V assets into a QA master.
Optionally applies the owner-reviewed frontal Bunny v06 -> v07 correction per
clip. Never calls AI APIs, downloads a model, authorizes publication, or
changes original assets. The repo stores code; original media stays private.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import sys
import time
from typing import Any, Callable

HEX = re.compile(r"^[a-f0-9]{64}$")
NAME = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
RUN_ID = re.compile(r"^(?:[a-z][a-z0-9_-]{1,47}|[a-f0-9]{32})$")
MAX_CLIPS = 40
MAX_CLIP_BYTES = 2_000_000_000
MAX_RECIPE_BYTES = 120_000
MAX_SECONDS_PER_CLIP = 180.0


class EpisodeAssemblyError(ValueError):
    """Invalid local recipe, unsupported media or failed gated assembly."""


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _required_file(file: str, checksum: str, root: Path) -> Path:
    if not isinstance(file, str) or not file.startswith("/"):
        raise EpisodeAssemblyError("Source paths must be explicit absolute paths.")
    source = Path(file).resolve()
    if not source.is_relative_to(root):
        raise EpisodeAssemblyError("Every source must remain within the private media root.")
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_CLIP_BYTES:
        raise EpisodeAssemblyError("Pinned source is missing, empty or oversized.")
    if not isinstance(checksum, str) or not HEX.fullmatch(checksum):
        raise EpisodeAssemblyError("Every source needs a lowercase SHA256 pin.")
    if digest(source) != checksum:
        raise EpisodeAssemblyError("Source changed since owner approved its SHA256.")
    return source


def _other_file(path: str) -> Path:
    if not isinstance(path, str) or not path.startswith("/"):
        raise EpisodeAssemblyError("Executables/scripts require explicit absolute paths.")
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise EpisodeAssemblyError("Required local executable/script missing.")
    return resolved


def _ensure_private(directory: Path) -> Path:
    target = directory.expanduser().resolve()
    if any((p / ".git").exists() for p in (target, *target.parents)):
        raise EpisodeAssemblyError("Private media must never be written inside Git.")
    return target


def _decode_duration(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EpisodeAssemblyError("ffprobe duration missing.") from exc
    if not 0.0 < number < 3600.0:
        raise EpisodeAssemblyError("Invalid video duration.")
    return number


def _run(args: list[str], *, timeout: int = 1200,
         abort_event: threading.Event | None = None) -> None:
    if any(not isinstance(x, str) or "\0" in x for x in args):
        raise EpisodeAssemblyError("Invalid executable arguments.")
    if abort_event is None:
        # Preserve the standalone/legacy synchronous offline assembler.
        try:
            response = subprocess.run(args, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, timeout=timeout,
                                      check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EpisodeAssemblyError("Local media command unavailable or timed out.") from exc
        if response.returncode:
            raise EpisodeAssemblyError(
                "Local media command failed: " +
                response.stderr.decode("utf-8", errors="replace")[-900:]
            )
        return
    if abort_event.is_set():
        raise EpisodeAssemblyError("Montage lease lost before command start.")
    # M54 monitored path: no unbounded stdout/stderr pipes, immediate
    # child-process termination when the Pi heartbeat flags lease loss.
    # Already-written files are kept in the private run directory for QA.
    with tempfile.TemporaryFile() as stderr:
        try:
            process=subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                     stderr=stderr,
                                     start_new_session=(os.name=="posix"))
        except OSError as exc:
            raise EpisodeAssemblyError("Local media command unavailable.") from exc
        def stop_child() -> None:
            if process.poll() is not None:
                return
            try:
                if os.name=="posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=3)
            except (OSError,subprocess.TimeoutExpired):
                if process.poll() is None:
                    try:
                        if os.name=="posix":
                            os.killpg(process.pid,signal.SIGKILL)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass
                    process.wait()
        try:
            deadline=time.monotonic()+timeout
            while process.poll() is None:
                if abort_event.is_set():
                    raise EpisodeAssemblyError(
                        "Montage lease lost; subprocess stopped and artifacts quarantined.")
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    raise EpisodeAssemblyError("Local montage process timed out.")
                try:
                    process.wait(timeout=min(0.25,remaining))
                except subprocess.TimeoutExpired:
                    continue
            if abort_event.is_set():
                raise EpisodeAssemblyError("Montage lease lost at subprocess completion.")
            if process.returncode:
                stderr.seek(0,os.SEEK_END)
                stderr.seek(max(0,stderr.tell()-900))
                raise EpisodeAssemblyError(
                    "Local media command failed: " +
                    stderr.read().decode("utf-8",errors="replace"))
        finally:
            stop_child()


def probe_video(file: Path, probe_executable: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [probe_executable, "-v", "error", "-show_entries",
             "format=duration:stream=index,codec_type,width,height",
             "-of", "json", str(file)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=True,
        )
        result = json.loads(completed.stdout.decode("utf-8"))
    except (OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, ValueError) as exc:
        raise EpisodeAssemblyError("ffprobe could not parse the candidate video.") from exc
    streams = result.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audio) != 1:
        raise EpisodeAssemblyError("Exactly one video and one audio stream required.")
    if not all(type(videos[0].get(k)) is int and videos[0][k] > 0
               for k in ("width", "height")):
        raise EpisodeAssemblyError("Invalid video geometry.")
    return {"width": videos[0]["width"], "height": videos[0]["height"],
            "duration": _decode_duration(result.get("format", {}).get("duration")),
            "audio_streams": len(audio)}


class EpisodeAssembler:
    """One explicit run from a local, owner-pinned, immutable source manifest."""

    def __init__(self, recipe_path: str | Path,
                 *, runner: Callable[..., None] = _run,
                 prober: Callable[[Path, str], dict[str, Any]] = probe_video):
        recipe_path = Path(recipe_path).expanduser().resolve()
        if not recipe_path.is_file() or recipe_path.stat().st_size > MAX_RECIPE_BYTES:
            raise EpisodeAssemblyError("Local recipe missing or oversized.")
        _ensure_private(recipe_path.parent)
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
        if not isinstance(recipe, dict) or set(recipe) != {
                "schema_version", "series_id", "episode_number", "script",
                "private_root", "output_root", "voice_rights",
                "tools", "clips"}:
            raise EpisodeAssemblyError("Invalid recipe keys.")
        if recipe["schema_version"] != 1:
            raise EpisodeAssemblyError("Unsupported episode recipe schema.")
        if not isinstance(recipe["series_id"], str) or not NAME.fullmatch(recipe["series_id"]):
            raise EpisodeAssemblyError("Invalid series identifier.")
        if type(recipe["episode_number"]) is not int or not 1 <= recipe["episode_number"] <= 120:
            raise EpisodeAssemblyError("Invalid episode number.")
        if recipe["voice_rights"] not in ("INTERNAL_TEST_ONLY", "COMMERCIAL_LICENSE_VERIFIED"):
            raise EpisodeAssemblyError("Voice rights declaration missing.")
        self.root = _ensure_private(Path(recipe["private_root"]))
        if not self.root.is_dir():
            raise EpisodeAssemblyError("Private asset root does not exist.")
        self.output_root = _ensure_private(Path(recipe["output_root"]))
        if not self.output_root.is_relative_to(self.root):
            raise EpisodeAssemblyError("Output root must be under private asset root.")
        if not isinstance(recipe["script"], dict) or set(recipe["script"]) != {"path", "sha256"}:
            raise EpisodeAssemblyError("Pinned approved script required.")
        self.script = _required_file(recipe["script"]["path"],
                                     recipe["script"]["sha256"], self.root)
        tools = recipe["tools"]
        if not isinstance(tools, dict) or set(tools) != {
                "ffmpeg", "ffprobe", "face_python", "face_v06", "face_v06_sha256",
                "face_v07", "face_v07_sha256"}:
            raise EpisodeAssemblyError("Required local tool configuration missing.")
        self.ffmpeg = str(_other_file(tools["ffmpeg"]))
        self.ffprobe = str(_other_file(tools["ffprobe"]))
        self.face_python = str(_other_file(tools["face_python"]))
        self.v06 = _required_file(tools["face_v06"], tools["face_v06_sha256"],self.root)
        self.v07 = _required_file(tools["face_v07"], tools["face_v07_sha256"],self.root)
        clips = recipe["clips"]
        if not isinstance(clips, list) or not 1 <= len(clips) <= MAX_CLIPS:
            raise EpisodeAssemblyError("A complete episode needs 1..40 source clips.")
        self.clips: list[dict[str, Any]] = []
        for item in clips:
            if not isinstance(item, dict) or set(item) != {
                    "video", "sha256", "face_cleanup"}:
                raise EpisodeAssemblyError("Clip must contain video, sha256, face_cleanup.")
            if item["face_cleanup"] not in ("none", "bunny_v07"):
                raise EpisodeAssemblyError("Unsupported face pipeline.")
            video = _required_file(item["video"],item["sha256"],self.root)
            self.clips.append({"path":video, "face_cleanup":item["face_cleanup"]})
        self.recipe = recipe
        self.recipe_path = recipe_path
        self.recipe_sha256 = digest(recipe_path)
        self.runner = runner
        self.prober = prober

    def preflight(self) -> dict[str, Any]:
        """Read-only validation: never runs TTS, LTX, rendering or face cleanup."""
        if digest(self.recipe_path) != self.recipe_sha256:
            raise EpisodeAssemblyError("Episode recipe changed after it was loaded.")
        _required_file(self.recipe["script"]["path"],
                       self.recipe["script"]["sha256"],self.root)
        _required_file(self.recipe["tools"]["face_v06"],
                       self.recipe["tools"]["face_v06_sha256"],self.root)
        _required_file(self.recipe["tools"]["face_v07"],
                       self.recipe["tools"]["face_v07_sha256"],self.root)
        clips = []
        for index,item in enumerate(self.clips):
            source=self.recipe["clips"][index]
            _required_file(source["video"],source["sha256"],self.root)
            information = self.prober(item["path"],self.ffprobe)
            if not .2 <= information["duration"] <= MAX_SECONDS_PER_CLIP:
                raise EpisodeAssemblyError("Clip too short/long for one scene.")
            if (item["face_cleanup"] == "bunny_v07" and
                    (information["width"],information["height"]) != (384,384)):
                raise EpisodeAssemblyError(
                    "Bunny v07 is approved only for original 384x384 frontal clips.")
            clips.append({**information,
                          "source_sha256":digest(item["path"]),
                          "face_cleanup":item["face_cleanup"]})
        return {
            "status":"READY_FOR_LOCAL_ASSEMBLY",
            "series_id":self.recipe["series_id"],
            "episode_number":self.recipe["episode_number"],
            "clips":clips, "script_sha256":digest(self.script),
            "voice_rights":self.recipe["voice_rights"],
            "source_duration_seconds":round(sum(x["duration"] for x in clips),3),
            "external_inference":False, "publication_approved":False,
        }

    def execute(self, *, run_id: str,
                abort_event: threading.Event | None = None) -> dict[str, Any]:
        from .resource_gate import cooperative_compute_lock
        with cooperative_compute_lock(self.root):
            return self._execute_reserved(run_id=run_id,abort_event=abort_event)

    def _execute_reserved(self, *, run_id: str,
                          abort_event: threading.Event | None = None) -> dict[str, Any]:
        if not isinstance(run_id,str) or not RUN_ID.fullmatch(run_id):
            raise EpisodeAssemblyError("Run id must be stable and safe.")
        evidence = self.preflight()
        run_dir = self.output_root / run_id
        if run_dir.exists():
            raise EpisodeAssemblyError("Run already exists: do not overwrite or retry blindly.")
        run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        record = {
            "schema_version":1, "run_id":run_id, "status":"STARTED",
            "started_at":time.time(), "recipe_sha256":digest(self.recipe_path),
            **evidence,
        }
        manifest = run_dir / "qa_report.json"
        manifest.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",
                            encoding="utf-8")
        try:
            def check_lease() -> None:
                if abort_event is not None and abort_event.is_set():
                    raise EpisodeAssemblyError(
                        "Montage lease lost; preserving private partial artifacts.")
            check_lease()
            normalized = []
            for index, clip in enumerate(self.clips,1):
                check_lease()
                base = clip["path"]
                if clip["face_cleanup"] == "bunny_v07":
                    middle = run_dir / f"{index:03}_v06.mp4"
                    face = run_dir / f"{index:03}_v07.mp4"
                    self.runner([self.face_python,str(self.v06),
                                 "--input",str(base),"--output",str(middle)],
                                 timeout=1500)
                    self.prober(middle,self.ffprobe)
                    self.runner([self.face_python,str(self.v07),
                                 "--input",str(middle),"--output",str(face)],
                                 timeout=1500)
                    base=face
                info = self.prober(base,self.ffprobe)
                if abs(info["duration"] - evidence["clips"][index-1]["duration"]) > .40:
                    raise EpisodeAssemblyError("Face processing changed the scene duration.")
                staged = run_dir / f"{index:03}_normalized.mp4"
                self.runner([
                    self.ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-n",
                    "-i",str(base),"-map","0:v:0","-map","0:a:0",
                    "-vf","scale=1280:720:force_original_aspect_ratio=decrease,"
                          "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p",
                    "-c:v","libx264","-preset","medium","-crf","18",
                    "-c:a","aac","-ar","48000","-ac","2","-b:a","160k",
                    "-movflags","+faststart",str(staged)],timeout=1800)
                report = self.prober(staged,self.ffprobe)
                if (report["width"],report["height"]) != (1280,720):
                    raise EpisodeAssemblyError("Normalized scene geometry mismatch.")
                if abs(report["duration"] - evidence["clips"][index-1]["duration"]) > .60:
                    raise EpisodeAssemblyError("Normalized scene changed duration.")
                normalized.append(staged)
                check_lease()
            # Paths are local-only, already generated filenames controlled by this module.
            listing = run_dir / "concat.ffconcat"
            listing.write_text("ffconcat version 1.0\n" +
                "".join(f"file '{p.name}'\n" for p in normalized),encoding="utf-8")
            master = run_dir / "episode_qa_master.mp4"
            # Stream-copying MP4 concat preserves the frames, but AAC priming
            # can shift packet timestamps at scene boundaries. FFprobe then
            # reports a non-CFR r_frame_rate even with 24fps normalized clips,
            # and M7 correctly rejects the purported 24fps final master.
            # Explicit final video fps normalization makes the delivered
            # master CFR; map and re-encode its audio track as well.
            check_lease()
            self.runner([self.ffmpeg,"-hide_banner","-loglevel","error",
                         "-nostdin","-n","-safe","0","-f","concat",
                         "-i",str(listing),"-map","0:v:0","-map","0:a:0",
                         "-vf","fps=24,format=yuv420p",
                         "-c:v","libx264","-preset","medium","-crf","18",
                         "-c:a","aac","-ar","48000","-ac","2","-b:a","160k",
                         "-movflags","+faststart",
                         str(master)],timeout=1800)
            final = self.prober(master,self.ffprobe)
            if (final["width"],final["height"]) != (1280,720):
                raise EpisodeAssemblyError("Final output geometry invalid.")
            if abs(final["duration"] - evidence["source_duration_seconds"]) > max(
                    0.75, .25*len(self.clips)):
                raise EpisodeAssemblyError("Final running time differs from scene sum.")
            check_lease()
            record.update({
                "status":"RENDERED_PENDING_HUMAN_AV_QA",
                "final_media_path":str(master),
                "final_media_sha256":digest(master),
                "final_media_bytes":master.stat().st_size,
                "final_duration_seconds":final["duration"],
                "clips_built":len(normalized),
                "completed_at":time.time(),
            })
        except Exception as exc:
            record["status"]="FAILED_REQUIRES_MANUAL_RECONCILIATION"
            record["failure_type"]=type(exc).__name__
            manifest.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",
                                encoding="utf-8")
            raise
        manifest.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",
                            encoding="utf-8")
        return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kidsstudio.episode_assembly")
    parser.add_argument("--recipe",type=Path,required=True)
    parser.add_argument("--preflight",action="store_true")
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--run-id")
    args=parser.parse_args(argv)
    if args.execute == args.preflight:
        parser.error("Choose exactly one of --preflight or --execute.")
    if args.execute and not args.run_id:
        parser.error("--execute needs an explicit immutable --run-id.")
    try:
        assembler=EpisodeAssembler(args.recipe)
        report=(assembler.execute(run_id=args.run_id) if args.execute
                else assembler.preflight())
    except (EpisodeAssemblyError,OSError,ValueError,KeyError,TypeError) as exc:
        print("EPISODE_ASSEMBLY_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
