"""M12: read-only Pi↔Mac *actual file* lineage for the one-scene pilot.

The M6 staged flow stores owner-approved voice/A2V SHA in Pi SQLite. The M4
assembler independently accepts local MP4 paths. This check bridges those
two truths: the EXACT current owner-approved LTX job's local A2V must be the
one pinned by the future montage recipe. An authenticated Pi queue receipt
is necessary but not sufficient without the actual local bytes and receipt.

Current M6 ledger is one WAV + one A2V job per episode. Multi-scene workflows
need a new per-scene ledger; this tool rejects multi-clip recipes instead of
silently claiming scene-level completeness. No render/upload/mutation occurs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

from .episode_assembly import EpisodeAssembler, EpisodeAssemblyError, digest, probe_video
from .studio_queue import StudioQueue

HEX=re.compile(r"^[a-f0-9]{64}$")
JOB=re.compile(r"^[a-f0-9]{32}$")
KIND_RECEIPTS={
    "voice_synthesize":("narration.wav","VOICE_RENDERED_PENDING_QA","wav"),
    "ltx_animate":("a2v.mp4","A2V_RENDERED_PENDING_QA","mp4"),
}


class AssemblyLineageError(ValueError):
    """Approved pipeline and exact scene input do not have matching provenance."""


def _private_root(directory: str | Path) -> Path:
    raw=Path(directory).expanduser()
    if not raw.is_absolute() or raw.is_symlink():
        raise AssemblyLineageError("Output root must be absolute and not symlinked.")
    root=raw.resolve()
    if not root.is_dir() or any((p/".git").exists() for p in (root,*root.parents)):
        raise AssemblyLineageError("Existing private Mac output root outside Git required.")
    return root


def _local_stage(root: Path, row: Any, job: Any, *,
                 expected_kind: str, script_sha256: str) -> tuple[Path,str]:
    name,status,media_type=KIND_RECEIPTS[expected_kind]
    if row["stage"]!=expected_kind or row["state"]!="QA_APPROVED":
        raise AssemblyLineageError("Both M6 stages require separate owner QA.")
    job_id=row["job_id"]
    if not isinstance(job_id,str) or not JOB.fullmatch(job_id):
        raise AssemblyLineageError("Invalid/stale stage job ID.")
    if job is None or job["kind"]!=expected_kind or job["state"]!="COMPLETED":
        raise AssemblyLineageError("Current Pi stage job was not completed.")
    try:
        server=json.loads(job["result_json"] or "{}")
    except (ValueError,TypeError) as exc:
        raise AssemblyLineageError("Pi media job receipt is invalid JSON.") from exc
    checksum=row["artifact_sha256"]
    if (not isinstance(checksum,str) or not HEX.fullmatch(checksum)
            or server.get("artifact_sha256")!=checksum
            or server.get("status")!=status or
            server.get("artifact_type")!=media_type or
            server.get("publication_approved") is not False or
            row["script_sha256"]!=script_sha256):
        raise AssemblyLineageError("M6 owner QA does not match Pi media receipt.")
    run_dir=root/job_id
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise AssemblyLineageError("Expected local immutable stage run folder missing.")
    artifact=run_dir/name
    receipt=run_dir/"stage_receipt.json"
    if (artifact.is_symlink() or receipt.is_symlink()
            or not artifact.is_file() or not receipt.is_file()
            or not 0<receipt.stat().st_size<=20000):
        raise AssemblyLineageError("Pinned Mac stage artifact/receipt unavailable.")
    try:
        local=json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise AssemblyLineageError("Mac stage receipt JSON invalid.") from exc
    if (not isinstance(local,dict) or
            local.get("job_id")!=job_id or local.get("stage")!=expected_kind
            or local.get("status")!=status
            or local.get("script_sha256")!=script_sha256
            or local.get("artifact_sha256")!=checksum
            or local.get("artifact_type")!=media_type
            or local.get("publication_approved") is not False
            or not isinstance(local.get("recipe_sha256"),str)
            or not HEX.fullmatch(local["recipe_sha256"])
            or not isinstance(local.get("artifact_bytes"),int)
            or local["artifact_bytes"]!=artifact.stat().st_size
            or not 0<artifact.stat().st_size<=2_000_000_000
            or digest(artifact)!=checksum):
        raise AssemblyLineageError("Actual Mac media bytes or receipt differ from Pi.")
    return artifact,checksum


def inspect_assembly_lineage(
    queue: StudioQueue,
    *,
    series_id: str,
    ordinal: int,
    voice_output_root: str | Path,
    ltx_output_root: str | Path,
    assembly_recipe: str | Path,
    video_prober: Callable[[Path,str],dict[str,Any]]=probe_video,
) -> dict[str,Any]:
    if not isinstance(series_id,str) or not re.fullmatch("[a-z][a-z0-9_-]{1,47}",series_id):
        raise AssemblyLineageError("Invalid series ID.")
    if type(ordinal) is not int or not 1<=ordinal<=120:
        raise AssemblyLineageError("Invalid episode ordinal.")
    voice_root=_private_root(voice_output_root)
    ltx_root=_private_root(ltx_output_root)
    with queue._connection() as db:
        ep=db.execute("""SELECT state,source_sha256 FROM studio_episodes
            WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
        if (ep is None or ep["state"]!="SCRIPT_APPROVED" or
            not isinstance(ep["source_sha256"],str) or
            not HEX.fullmatch(ep["source_sha256"])):
            raise AssemblyLineageError("Current owner-approved original script required.")
        script_hash=ep["source_sha256"]
        rows=db.execute("""SELECT * FROM studio_episode_stages
            WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchall()
        by_kind={row["stage"]:row for row in rows}
        if set(by_kind)!=set(KIND_RECEIPTS) or len(rows)!=2:
            raise AssemblyLineageError("M6 voice and LTX lineage must both exist.")
        voice=by_kind["voice_synthesize"]
        ltx=by_kind["ltx_animate"]
        if ltx["source_voice_sha256"]!=voice["artifact_sha256"]:
            raise AssemblyLineageError("Current LTX job does not cite approved voice.")
        jobs={}
        for kind,row in by_kind.items():
            jobs[kind]=db.execute("""SELECT kind,state,result_json FROM jobs
                WHERE job_id=?""",(row["job_id"],)).fetchone()
        audio_table=db.execute("""SELECT 1 FROM sqlite_master WHERE
            name='studio_audio_checks' AND type='table'""").fetchone()
        if audio_table:
            audio=db.execute("""SELECT voice_sha256,a2v_sha256,status
                FROM studio_audio_checks WHERE series_id=? AND ordinal=?
                  AND ltx_job_id=?""",(series_id,ordinal,ltx["job_id"])).fetchone()
            if (audio is None or
                audio["voice_sha256"]!=voice["artifact_sha256"] or
                audio["a2v_sha256"]!=ltx["artifact_sha256"] or
                audio["status"]!="TECH_COMPATIBLE_OWNER_LIPSYNC_REVIEW_PENDING"):
                raise AssemblyLineageError("Current M10 audio technical evidence missing.")
    voice_file,voice_sha=_local_stage(
        voice_root,voice,jobs["voice_synthesize"],
        expected_kind="voice_synthesize",script_sha256=script_hash)
    video_file,video_sha=_local_stage(
        ltx_root,ltx,jobs["ltx_animate"],
        expected_kind="ltx_animate",script_sha256=script_hash)
    assembler=EpisodeAssembler(assembly_recipe,prober=video_prober)
    if (assembler.recipe["series_id"]!=series_id or
            assembler.recipe["episode_number"]!=ordinal or
            assembler.recipe["script"]["sha256"]!=script_hash):
        raise AssemblyLineageError("Assembly recipe targets another episode or script.")
    if len(assembler.recipe["clips"])!=1:
        raise AssemblyLineageError(
            "Current one-stage-per-episode M6 ledger supports ONE clip only. "
            "Implement scene-level jobs before claiming a multi-scene episode.")
    clip=assembler.recipe["clips"][0]
    if (Path(clip["video"]).resolve()!=video_file or
            clip["sha256"]!=video_sha):
        raise AssemblyLineageError("Assembly clip is not the actual approved LTX output.")
    # Real ffprobe by default; synthetic test injects a bounded fake.
    checked=assembler.preflight()
    return {
        "schema_version":1,
        "status":"SINGLE_SCENE_ASSEMBLY_INPUT_VERIFIED_NOT_RENDERED",
        "series_id":series_id,"episode_number":ordinal,
        "voice_job_id":voice["job_id"],
        "ltx_job_id":ltx["job_id"],
        "approved_script_sha256":script_hash,
        "actual_voice_sha256":voice_sha,"actual_ltx_sha256":video_sha,
        "assembly_recipe_sha256":assembler.recipe_sha256,
        "scene_count":1,
        "technical_audio_evidence":bool(audio_table),
        "animation_performed_now":False,
        "assembly_performed_now":False,
        "owner_final_episode_qa_complete":False,
        "public_release_authorized":False,
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog="studio-assembly-lineage")
    p.add_argument("--db",required=True,type=Path)
    p.add_argument("--series",required=True)
    p.add_argument("--episode",required=True,type=int)
    p.add_argument("--voice-output-root",required=True,type=Path)
    p.add_argument("--ltx-output-root",required=True,type=Path)
    p.add_argument("--assembly-recipe",required=True,type=Path)
    args=p.parse_args(argv)
    try:
        result=inspect_assembly_lineage(
            StudioQueue(args.db),series_id=args.series,ordinal=args.episode,
            voice_output_root=args.voice_output_root,
            ltx_output_root=args.ltx_output_root,
            assembly_recipe=args.assembly_recipe)
    except (AssemblyLineageError,EpisodeAssemblyError,OSError,
            ValueError,TypeError,KeyError) as exc:
        print("STUDIO_ASSEMBLY_HANDOFF_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
