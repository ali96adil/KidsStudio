"""Local voice/LTX source preflight and immutable episode recipe authoring.

No inference, no cloud APIs, no downloads, no implicit provider fallback.
Reads only explicitly approved private files and probes media. It does NOT
assert that the embedded A2V narration matches the Chatterbox WAV by ear.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from .episode_assembly import (
    EpisodeAssemblyError, _required_file, _ensure_private, _other_file,
    _decode_duration, digest, probe_video
)


class SourceError(EpisodeAssemblyError):
    """Invalid or unverified local voice / animation source contract."""


def probe_voice(path: Path, executable: str) -> dict[str, Any]:
    """WAV check via local ffprobe: one audio track and no video tracks."""
    try:
        completed=subprocess.run(
            [executable,"-v","error","-show_entries",
             "format=duration:stream=codec_type,codec_name,sample_rate",
             "-of","json",str(path)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            timeout=30,check=True)
        data=json.loads(completed.stdout.decode("utf-8"))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        raise SourceError("ffprobe cannot read approved narration.") from exc
    streams=data.get("streams",[])
    sound=[s for s in streams if s.get("codec_type")=="audio"]
    picture=[s for s in streams if s.get("codec_type")=="video"]
    if len(sound)!=1 or picture:
        raise SourceError("One voice audio stream and zero video streams required.")
    return {"duration":_decode_duration(data.get("format",{}).get("duration")),
            "audio_streams":1}


class EpisodeSourcePreflight:
    """Verify pinned sources for a *previously generated* Chatterbox/LTX episode."""
    def __init__(self, plan: str | Path,
                 *, voice_prober: Callable[[Path,str],dict[str,Any]] = probe_voice,
                 video_prober: Callable[[Path,str],dict[str,Any]] = probe_video):
        plan_path=Path(plan).expanduser().resolve()
        if not plan_path.is_file() or plan_path.stat().st_size > 120_000:
            raise SourceError("Missing or oversized private source manifest.")
        _ensure_private(plan_path.parent)
        data=json.loads(plan_path.read_text(encoding="utf-8"))
        if not isinstance(data,dict) or set(data)!={
            "schema_version","series_id","episode_number","language",
            "private_root","output_root","voice_rights","script","tools","scenes"
        }:
            raise SourceError("Source manifest keys are incomplete/unknown.")
        if data["schema_version"]!=1 or data["language"] not in ("ar","en"):
            raise SourceError("Invalid source manifest version/language.")
        if (not isinstance(data["series_id"],str) or
            not isinstance(data["episode_number"],int) or
            type(data["episode_number"]) is bool or
            not 1<=data["episode_number"]<=120):
            raise SourceError("Invalid episode identity.")
        import re
        if not re.fullmatch("[a-z][a-z0-9_-]{1,47}",data["series_id"]):
            raise SourceError("Invalid series identifier.")
        if data["voice_rights"] not in ("INTERNAL_TEST_ONLY","COMMERCIAL_LICENSE_VERIFIED"):
            raise SourceError("Untracked voice rights.")
        self.root=_ensure_private(Path(data["private_root"]))
        if not self.root.is_dir():
            raise SourceError("Private root unavailable.")
        target=_ensure_private(Path(data["output_root"]))
        if not target.is_relative_to(self.root):
            raise SourceError("Output root must stay under the private root.")
        script=data["script"]
        if not isinstance(script,dict) or set(script)!={"path","sha256"}:
            raise SourceError("Approved script must include source path/SHA256.")
        _required_file(script["path"],script["sha256"],self.root)
        tools=data["tools"]
        if not isinstance(tools,dict) or set(tools)!={
            "ffmpeg","ffprobe","face_python","face_v06","face_v06_sha256",
            "face_v07","face_v07_sha256"
        }:
            raise SourceError("Explicit assembly tools are required.")
        self.ffprobe=str(_other_file(tools["ffprobe"]))
        _other_file(tools["ffmpeg"])
        _other_file(tools["face_python"])
        _required_file(tools["face_v06"],tools["face_v06_sha256"],self.root)
        _required_file(tools["face_v07"],tools["face_v07_sha256"],self.root)
        scenes=data["scenes"]
        if not isinstance(scenes,list) or not 1<=len(scenes)<=40:
            raise SourceError("Require 1..40 numbered scenes.")
        seen_voice=set()
        seen_video=set()
        for i,scene in enumerate(scenes,1):
            if not isinstance(scene,dict) or set(scene)!={
                "scene","voice_wav","voice_sha256","ltx_video",
                "ltx_sha256","source_voice_sha256","face_cleanup"
            }:
                raise SourceError("Scene source contract missing fields.")
            if type(scene["scene"]) is not int or scene["scene"]!=i:
                raise SourceError("Scene numbers must be contiguous from 1.")
            if scene["face_cleanup"] not in ("none","bunny_v07"):
                raise SourceError("Unapproved face correction name.")
            if scene["source_voice_sha256"]!=scene["voice_sha256"]:
                raise SourceError("LTX provenance does not reference chosen voice.")
            voice=_required_file(scene["voice_wav"],scene["voice_sha256"],self.root)
            video=_required_file(scene["ltx_video"],scene["ltx_sha256"],self.root)
            if voice.suffix.lower() != ".wav" or video.suffix.lower() != ".mp4":
                raise SourceError("Expected pinned WAV narration + MP4 A2V.")
            if video in seen_video:
                raise SourceError("Duplicate LTX video used for multiple scenes.")
            seen_voice.add(voice);seen_video.add(video)
        self.plan=data
        self.plan_path=plan_path
        self.plan_digest=digest(plan_path)
        self.output_root=target
        self.voice_prober=voice_prober
        self.video_prober=video_prober

    def preflight(self) -> dict[str,Any]:
        if digest(self.plan_path)!=self.plan_digest:
            raise SourceError("Source plan changed after being opened.")
        plan=self.plan
        _required_file(plan["script"]["path"],plan["script"]["sha256"],self.root)
        for key in ("face_v06","face_v07"):
            _required_file(plan["tools"][key],plan["tools"][key+"_sha256"],self.root)
        rows=[]
        for scene in plan["scenes"]:
            wav=_required_file(scene["voice_wav"],scene["voice_sha256"],self.root)
            a2v=_required_file(scene["ltx_video"],scene["ltx_sha256"],self.root)
            voice=self.voice_prober(wav,self.ffprobe)
            video=self.video_prober(a2v,self.ffprobe)
            if not 0.2<=voice["duration"]<=180:
                raise SourceError("Voice duration outside bounded range.")
            if not 0.2<=video["duration"]<=180:
                raise SourceError("Video duration outside bounded range.")
            if voice["duration"]>video["duration"]+0.8:
                raise SourceError("Narration is longer than A2V clip.")
            if scene["face_cleanup"]=="bunny_v07" and (
                    video["width"],video["height"])!=(384,384):
                raise SourceError("Bunny cleanup only for calibrated 384x384 front view.")
            rows.append({
                "scene":scene["scene"],
                "voice_sha256":digest(wav),
                "a2v_sha256":digest(a2v),
                "voice_seconds":voice["duration"],
                "a2v_seconds":video["duration"],
                "face_cleanup":scene["face_cleanup"],
                "voice_and_video_timing":"TECHNICAL_DURATION_CHECK_ONLY",
                "voice_identity_or_lipsync":"HUMAN_QA_REQUIRED",
            })
        return {
            "status":"MEDIA_SOURCES_PROBED_AWAITING_OWNER_QA",
            "series_id":plan["series_id"],
            "episode_number":plan["episode_number"],
            "script_sha256":digest(Path(plan["script"]["path"])),
            "voice_rights":plan["voice_rights"],
            "scenes":rows,
            "publishing_approved":False,
            "inference_performed":False,
        }

    def write_assembly_recipe(self, destination: str | Path) -> dict[str,Any]:
        report=self.preflight()
        destination=Path(destination).expanduser().resolve()
        if not destination.is_relative_to(self.root):
            raise SourceError("Assembly recipe must stay inside private media root.")
        if destination.suffix!=".json" or destination.exists():
            raise SourceError("Assembly recipe must be new and end in .json.")
        target={
            "schema_version":1,
            "series_id":self.plan["series_id"],
            "episode_number":self.plan["episode_number"],
            "private_root":str(self.root),
            "output_root":str(self.output_root),
            "voice_rights":self.plan["voice_rights"],
            "script":self.plan["script"],
            "tools":self.plan["tools"],
            "clips":[{
                "video":scene["ltx_video"],"sha256":scene["ltx_sha256"],
                "face_cleanup":scene["face_cleanup"]
            } for scene in self.plan["scenes"]],
        }
        # File is not automatically approved by creating it; a Mac operator
        # must explicitly inspect it before adding its SHA to MediaRecipes.
        destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        raw=(json.dumps(target,indent=2,ensure_ascii=False)+"\n").encode("utf-8")
        fd=os.open(str(destination),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as output:
            output.write(raw)
            output.flush();os.fsync(output.fileno())
        return {**report,"assembly_recipe_path":str(destination),
                "assembly_recipe_sha256":digest(destination),
                "owner_approval_required":True}


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(prog="studio-source-preflight")
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--write-assembly-recipe",type=Path)
    args=p.parse_args(argv)
    try:
        planner=EpisodeSourcePreflight(args.plan)
        result=(planner.write_assembly_recipe(args.write_assembly_recipe)
            if args.write_assembly_recipe else planner.preflight())
    except (SourceError,EpisodeAssemblyError,OSError,ValueError,TypeError,KeyError) as exc:
        print("STUDIO_SOURCE_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
