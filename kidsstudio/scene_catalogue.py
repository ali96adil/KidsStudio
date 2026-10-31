"""M14: explicit private catalogue freeze for approved multi-scene montage.

M13 records are verified against the actual Mac stage bytes at freeze time.
A hash-pinned local evidence file lets the M6 Mac worker re-check the same
ordered media before FFmpeg; Pi never provides arbitrary filesystem paths.

This is an OWNER-controlled hash pin, not a digital signature or substitute
for the future owner video review. Neither command renders/uploads media.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable

from .episode_assembly import EpisodeAssembler, digest, probe_video, _ensure_private
from .assembly_lineage import _local_stage, _private_root
from .scene_assembly import inspect_scene_assembly
from .studio_queue import StudioQueue

SHA = re.compile(r"^[a-f0-9]{64}$")
JOB = re.compile(r"^[a-f0-9]{32}$")
RECIPE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class SceneCatalogueError(ValueError):
    """Scene-to-montage approval evidence is incomplete or changed."""


def _private_json(path: str | Path, root: Path, *, exists: bool) -> Path:
    raw=Path(path).expanduser()
    if not raw.is_absolute() or raw.is_symlink():
        raise SceneCatalogueError("Use a new absolute private non-symlink JSON file.")
    target=raw.resolve()
    if not target.is_relative_to(root) or target.suffix!=".json":
        raise SceneCatalogueError("Manifest must remain inside approved private root.")
    if exists and (not target.is_file() or not 0<target.stat().st_size<=150_000):
        raise SceneCatalogueError("Evidence file missing or oversized.")
    if not exists and (target.exists() or target.is_symlink()):
        raise SceneCatalogueError("Owner evidence filename is already reserved.")
    return target


def verify_scene_seal(episode_recipe: str | Path, evidence_file: str | Path) -> dict:
    """Offline runtime read-only validation used by MediaRecipes.resolve()."""
    assembler=EpisodeAssembler(episode_recipe)
    root=assembler.root
    proof=_private_json(evidence_file,root,exists=True)
    try:
        seal=json.loads(proof.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise SceneCatalogueError("Invalid private scene evidence JSON.") from exc
    required={"schema_version","series_id","episode_number","script_sha256",
              "assembly_recipe_sha256","scene_plan_sha256",
              "voice_output_root","ltx_output_root","scenes",
              "publication_approved"}
    if not isinstance(seal,dict) or set(seal)!=required:
        raise SceneCatalogueError("Unrecognized scene seal format.")
    if (seal["schema_version"]!=1 or
        seal["series_id"]!=assembler.recipe["series_id"] or
        seal["episode_number"]!=assembler.recipe["episode_number"] or
        seal["script_sha256"]!=assembler.recipe["script"]["sha256"] or
        seal["assembly_recipe_sha256"]!=assembler.recipe_sha256 or
        not isinstance(seal["scene_plan_sha256"],str) or
        not SHA.fullmatch(seal["scene_plan_sha256"]) or
        seal["publication_approved"] is not False):
        raise SceneCatalogueError("Scene seal references a different approved episode.")
    clips=assembler.recipe["clips"]
    scenes=seal["scenes"]
    if (not isinstance(scenes,list) or not 2<=len(scenes)<=40
            or len(scenes)!=len(clips)):
        raise SceneCatalogueError("A complete ordered multi-scene seal is required.")
    voice_root=_private_root(seal["voice_output_root"])
    ltx_root=_private_root(seal["ltx_output_root"])
    for pos,(scene,clip) in enumerate(zip(scenes,clips),1):
        expected={"scene","scene_script_sha256","voice_job_id","ltx_job_id",
                  "voice_sha256","ltx_sha256"}
        if not isinstance(scene,dict) or set(scene)!=expected or scene["scene"]!=pos:
            raise SceneCatalogueError("Scene seal order/fields changed.")
        if (not isinstance(scene["scene_script_sha256"],str)
                or not SHA.fullmatch(scene["scene_script_sha256"])):
            raise SceneCatalogueError("Scene script hash missing.")
        for kind,jobkey,hashkey,rootdir,status,typ in (
            ("voice_synthesize","voice_job_id","voice_sha256",
             voice_root,"VOICE_RENDERED_PENDING_QA","wav"),
            ("ltx_animate","ltx_job_id","ltx_sha256",
             ltx_root,"A2V_RENDERED_PENDING_QA","mp4"),
        ):
            identifier=scene[jobkey];checksum=scene[hashkey]
            if (not isinstance(identifier,str) or not JOB.fullmatch(identifier)
                    or not isinstance(checksum,str) or not SHA.fullmatch(checksum)):
                raise SceneCatalogueError("Invalid scene job identity or media SHA.")
            row={"stage":kind,"state":"QA_APPROVED",
                 "job_id":identifier,"artifact_sha256":checksum,
                 "script_sha256":scene["scene_script_sha256"]}
            job={"kind":kind,"state":"COMPLETED",
                 "result_json":json.dumps({
                    "status":status,"artifact_sha256":checksum,
                    "artifact_type":typ,"publication_approved":False})}
            try:
                media,actual=_local_stage(rootdir,row,job,
                    expected_kind=kind,script_sha256=scene["scene_script_sha256"])
            except (ValueError,TypeError,KeyError,OSError) as exc:
                raise SceneCatalogueError("Actual private stage files changed.") from exc
            if actual!=checksum:
                raise SceneCatalogueError("Source scene hash does not agree with the seal.")
            if kind=="ltx_animate":
                if Path(clip["video"]).resolve()!=media or clip["sha256"]!=checksum:
                    raise SceneCatalogueError("Montage clip differs from approved LTX output.")
                receipt=json.loads((rootdir/identifier/"stage_receipt.json").read_text())
                if receipt.get("source_voice_sha256")!=scene["voice_sha256"]:
                    raise SceneCatalogueError("Local LTX was not produced from selected WAV.")
    return {"status":"PINNED_MULTISCENE_CATALOGUE_VERIFIED_NOT_RENDERED",
            "scene_count":len(scenes),
            "episode_recipe_sha256":assembler.recipe_sha256,
            "scene_evidence_sha256":digest(proof),
            "rendered":False,"publication_approved":False}


def freeze_scene_catalogue(
    queue: StudioQueue, *,
    template: str | Path,
    assembly_recipe: str | Path,
    series_id: str,
    ordinal: int,
    voice_output_root: str | Path,
    ltx_output_root: str | Path,
    evidence_path: str | Path,
    catalog_path: str | Path,
    recipe_id: str,
    video_prober: Callable=probe_video,
) -> dict:
    """Explicitly writes two NEW owner-owned files, not remotely initiated."""
    if not isinstance(recipe_id,str) or not RECIPE_ID.fullmatch(recipe_id):
        raise SceneCatalogueError("Fixed approved local recipe ID required.")
    assembly=EpisodeAssembler(assembly_recipe,prober=video_prober)
    root=assembly.root
    evidence_target=_private_json(evidence_path,root,exists=False)
    catalog_target=_private_json(catalog_path,root,exists=False)
    if evidence_target==catalog_target:
        raise SceneCatalogueError("Evidence and catalogue must be separate files.")
    recipe,report=inspect_scene_assembly(
        queue,template=template,series_id=series_id,ordinal=ordinal,
        voice_output_root=voice_output_root,ltx_output_root=ltx_output_root,
        video_prober=video_prober)
    if recipe!=assembly.recipe:
        raise SceneCatalogueError("Saved M4 recipe differs from currently approved M13 scene outputs.")
    assembly.preflight()
    with queue._connection() as db:
        record=db.execute("""SELECT plan_sha256 FROM studio_scene_plans
            WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
        if not record or not SHA.fullmatch(record["plan_sha256"]):
            raise SceneCatalogueError("Current immutable plan receipt missing.")
        scripts={row["scene"]:row["script_sha256"] for row in db.execute("""
            SELECT scene,script_sha256 FROM studio_scenes
            WHERE series_id=? AND ordinal=?""",(series_id,ordinal))}
    seal={
        "schema_version":1,
        "series_id":series_id,
        "episode_number":ordinal,
        "script_sha256":recipe["script"]["sha256"],
        "assembly_recipe_sha256":digest(Path(assembly_recipe)),
        "scene_plan_sha256":record["plan_sha256"],
        "voice_output_root":str(_private_root(voice_output_root)),
        "ltx_output_root":str(_private_root(ltx_output_root)),
        "scenes":[{
            "scene":x["scene"],
            "scene_script_sha256":scripts[x["scene"]],
            "voice_job_id":x["voice_job_id"],
            "ltx_job_id":x["ltx_job_id"],
            "voice_sha256":x["voice_sha256"],
            "ltx_sha256":x["ltx_sha256"],
        } for x in report["scene_receipts"]],
        "publication_approved":False,
    }
    # Must create both files exactly once; no modification of original media.
    # A partial failed freeze remains visibly incomplete and cannot validate.
    evidence_target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    catalog_target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with evidence_target.open("x",encoding="utf-8") as output:
        os.chmod(evidence_target,0o600)
        json.dump(seal,output,indent=2,ensure_ascii=False)
        output.write("\n");output.flush();os.fsync(output.fileno())
    check=verify_scene_seal(assembly_recipe,evidence_target)
    catalogue={"schema_version":1,"recipes":{recipe_id:{
        "kind":"episode_assemble",
        "output_root":recipe["output_root"],
        "inputs":{"episode_recipe":str(Path(assembly_recipe).resolve()),
                  "scene_evidence":str(evidence_target)},
        "sha256":{"episode_recipe":assembly.recipe_sha256,
                  "scene_evidence":check["scene_evidence_sha256"]},
    }}}
    with catalog_target.open("x",encoding="utf-8") as output:
        os.chmod(catalog_target,0o600)
        json.dump(catalogue,output,indent=2,ensure_ascii=False)
        output.write("\n");output.flush();os.fsync(output.fileno())
    return {**check,"status":"MULTISCENE_MEDIA_CATALOGUE_FROZEN_NOT_EXECUTED",
            "recipe_id":recipe_id,"catalogue_sha256":digest(catalog_target),
            "catalogue_created":True,"rendered":False}


def main(argv=None)->int:
    p=argparse.ArgumentParser(prog="studio-scene-catalogue")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--template",type=Path,required=True)
    p.add_argument("--assembly-recipe",type=Path,required=True)
    p.add_argument("--series",required=True)
    p.add_argument("--episode",type=int,required=True)
    p.add_argument("--voice-output-root",type=Path,required=True)
    p.add_argument("--ltx-output-root",type=Path,required=True)
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--catalogue",type=Path,required=True)
    p.add_argument("--recipe-id",required=True)
    args=p.parse_args(argv)
    try:
        report=freeze_scene_catalogue(
            StudioQueue(args.db),template=args.template,
            assembly_recipe=args.assembly_recipe,series_id=args.series,
            ordinal=args.episode,voice_output_root=args.voice_output_root,
            ltx_output_root=args.ltx_output_root,evidence_path=args.evidence,
            catalog_path=args.catalogue,recipe_id=args.recipe_id)
    except (SceneCatalogueError,OSError,ValueError,KeyError,TypeError) as exc:
        print("STUDIO_MULTISCENE_CATALOGUE_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
