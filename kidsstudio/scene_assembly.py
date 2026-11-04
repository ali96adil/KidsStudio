"""M13 exact ordered scene-to-episode recipe construction, owner-controlled.

Reads Pi Studio Brain and exact local Mac media. All scene WAV/A2V files and
receipts must agree with current approved Pi job records. Writes only a NEW
explicitly requested private M4 recipe, never executes rendering.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any,Callable

from .studio_queue import StudioQueue
from .studio_scenes import assert_scenes_ready,SceneError
from .assembly_lineage import _private_root,_local_stage,AssemblyLineageError
from .episode_assembly import EpisodeAssembler,EpisodeAssemblyError,digest,probe_video


class SceneAssemblyError(ValueError):
    pass


def inspect_scene_assembly(
    queue:StudioQueue,
    *,
    template:str|Path,
    series_id:str,
    ordinal:int,
    voice_output_root:str|Path,
    ltx_output_root:str|Path,
    video_prober:Callable[[Path,str],dict[str,Any]]=probe_video,
)->tuple[dict,dict]:
    file=Path(template).expanduser()
    if not file.is_absolute() or file.is_symlink():
        raise SceneAssemblyError("Template must be a private absolute JSON file.")
    file=file.resolve()
    if not file.is_file() or not 0<file.stat().st_size<=100000:
        raise SceneAssemblyError("Missing or oversized owner template.")
    if any((p/".git").exists() for p in (file.parent,*file.parents)):
        raise SceneAssemblyError("Private template must stay outside Git.")
    try:source=json.loads(file.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:raise SceneAssemblyError("Invalid recipe template.") from exc
    required={"schema_version","series_id","episode_number","private_root",
              "output_root","script","voice_rights","tools","face_cleanup_by_scene"}
    if not isinstance(source,dict) or set(source)!=required or source["schema_version"]!=1:
        raise SceneAssemblyError("Expected exact M13 assembly template schema.")
    if source["series_id"]!=series_id or source["episode_number"]!=ordinal:
        raise SceneAssemblyError("Template belongs to a different episode.")
    with queue._connection() as db:
        ep=db.execute("""SELECT state,source_sha256 FROM studio_episodes
            WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
        if not ep or ep["state"]!="SCRIPT_APPROVED":
            raise SceneAssemblyError("Owner-approved parent episode script required.")
        scene_rows=assert_scenes_ready(db,series_id,ordinal,ep["source_sha256"])
        if (not isinstance(source["script"],dict) or
            source["script"].get("sha256")!=ep["source_sha256"]):
            raise SceneAssemblyError("Template must pin current approved parent script.")
        results=[]
        for scene in scene_rows:
            lookup={}
            for kind in ("voice_synthesize","ltx_animate"):
                stage=db.execute("""SELECT * FROM studio_scene_stages
                    WHERE series_id=? AND ordinal=? AND scene=? AND stage=?""",
                    (series_id,ordinal,scene["scene"],kind)).fetchone()
                job=db.execute("SELECT kind,state,result_json FROM jobs WHERE job_id=?",
                               (stage["job_id"],)).fetchone()
                normalized=dict(stage)
                normalized["script_sha256"]=stage["scene_script_sha256"]
                lookup[kind]=(normalized,job)
            results.append((scene,lookup))
    cleanup=source["face_cleanup_by_scene"]
    if (not isinstance(cleanup,list) or len(cleanup)!=len(results) or
        any(x not in ("none","bunny_v07") for x in cleanup)):
        raise SceneAssemblyError("Every scene needs explicit face-cleanup decision.")
    voice_root=_private_root(voice_output_root)
    ltx_root=_private_root(ltx_output_root)
    clips=[]
    matched=[]
    for scene,stages in results:
        wav,voice_sha=_local_stage(
            voice_root,*stages["voice_synthesize"],
            expected_kind="voice_synthesize",script_sha256=scene["script_sha256"])
        video,video_sha=_local_stage(
            ltx_root,*stages["ltx_animate"],
            expected_kind="ltx_animate",script_sha256=scene["script_sha256"])
        if (voice_sha!=scene["voice_sha256"] or
            video_sha!=scene["ltx_sha256"]):
            raise SceneAssemblyError("Mac outputs differ from the approved scene media.")
        clips.append({"video":str(video),"sha256":video_sha,
                      "face_cleanup":cleanup[scene["scene"]-1]})
        matched.append({"scene":scene["scene"],
                        "voice_job_id":scene["voice_job_id"],
                        "ltx_job_id":scene["ltx_job_id"],
                        "voice_sha256":voice_sha,"ltx_sha256":video_sha})
    target={key:value for key,value in source.items() if key!="face_cleanup_by_scene"}
    target["clips"]=clips
    # Exercise the same M4 preflight checks without materializing a recipe:
    from .episode_assembly import _ensure_private,_required_file,_other_file
    root=_ensure_private(Path(target["private_root"]))
    if not root.is_dir():
        raise SceneAssemblyError("Private episode asset root missing.")
    if not _ensure_private(Path(target["output_root"])).is_relative_to(root):
        raise SceneAssemblyError("Assembly output must remain private.")
    _required_file(target["script"]["path"],target["script"]["sha256"],root)
    tools=target["tools"]
    if not isinstance(tools,dict) or set(tools)!={
            "ffmpeg","ffprobe","face_python","face_v06","face_v06_sha256",
            "face_v07","face_v07_sha256"}:
        raise SceneAssemblyError("M4 tools must be explicitly pinned.")
    for name in ("ffmpeg","ffprobe","face_python"):
        _other_file(tools[name])
    for name in ("face_v06","face_v07"):
        _required_file(tools[name],tools[name+"_sha256"],root)
    durations=[]
    for clip in clips:
        candidate=_required_file(clip["video"],clip["sha256"],root)
        info=video_prober(candidate,tools["ffprobe"])
        if (not .2<=info["duration"]<=180 or
            clip["face_cleanup"]=="bunny_v07" and
            (info["width"],info["height"])!=(384,384)):
            raise SceneAssemblyError("One scene fails the approved M4 clip profile.")
        durations.append(info["duration"])
    return target,{
        "schema_version":1,
        "status":"ALL_SCENES_VERIFIED_ASSEMBLY_NOT_RENDERED",
        "series_id":series_id,"episode_number":ordinal,
        "scene_count":len(clips),"scene_receipts":matched,
        "template_sha256":digest(file),
        "estimated_source_duration_seconds":round(sum(durations),3),
        "generated_recipe":False,"rendered":False,
        "publication_approved":False
    }


def write_scene_recipe(target_file: str|Path, recipe:dict, evidence:dict) -> dict:
    path=Path(target_file).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise SceneAssemblyError("Destination must be absolute private path.")
    path=path.resolve()
    private=Path(recipe["private_root"]).resolve()
    if not path.is_relative_to(private) or path.suffix!=".json" or path.exists():
        raise SceneAssemblyError("New private M4 recipe path required; no overwrite.")
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    raw=(json.dumps(recipe,ensure_ascii=False,indent=2)+"\n").encode("utf-8")
    fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    return {**evidence,"status":"M4_RECIPE_CREATED_OWNER_REVIEW_REQUIRED",
            "generated_recipe":True,
            "recipe_sha256":digest(path),
            "rendered":False,"publication_approved":False}


def main(argv=None)->int:
    p=argparse.ArgumentParser(prog="studio-scene-assembly")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--template",type=Path,required=True)
    p.add_argument("--series",required=True)
    p.add_argument("--episode",type=int,required=True)
    p.add_argument("--voice-output-root",type=Path,required=True)
    p.add_argument("--ltx-output-root",type=Path,required=True)
    p.add_argument("--write-recipe",type=Path)
    args=p.parse_args(argv)
    try:
        recipe,report=inspect_scene_assembly(
            StudioQueue(args.db),template=args.template,
            series_id=args.series,ordinal=args.episode,
            voice_output_root=args.voice_output_root,
            ltx_output_root=args.ltx_output_root)
        if args.write_recipe:
            report=write_scene_recipe(args.write_recipe,recipe,report)
    except (SceneError,SceneAssemblyError,AssemblyLineageError,
            EpisodeAssemblyError,OSError,ValueError,KeyError,TypeError) as exc:
        print("SCENE_ASSEMBLY_NOT_READY: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
