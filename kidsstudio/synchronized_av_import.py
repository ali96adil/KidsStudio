"""M37 signed local synchronized AV review -> current Pi M10/M28.

Default is read-only, execute can import exactly the current LTX job's
independent evidence; M28 itself checks all source, rights, frames and roles.
No model invocation or publication API is reachable here.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys

from .scene_ai_qa import SceneAIGate, SceneError, _private
from .studio_scenes import SceneLedger, SHA
from .studio_queue import StudioQueue, QueueError


class AVImportError(ValueError):
    pass


def _read(path: str|Path) -> tuple[dict,str]:
    raw,sha=_private(path,100000,".json")
    try:value=json.loads(raw)
    except (UnicodeError,ValueError) as exc:
        raise AVImportError("Invalid signed AV report.") from exc
    if not isinstance(value,dict):
        raise AVImportError("AV report must be JSON object.")
    return value,sha


def import_synchronized(*,queue:StudioQueue,series_id:str,episode:int,
                        scene:int,report_dir:str|Path,m10_report:str|Path,
                        rights_file:str|Path,runner_key:bytes,
                        execute:bool=False)->dict:
    if (not isinstance(series_id,str) or not series_id or
        type(episode) is not int or not 1<=episode<=120 or
        type(scene) is not int or not 1<=scene<=40 or
        type(execute) is not bool or not isinstance(runner_key,bytes) or
        len(runner_key)<32):
        raise AVImportError("Current episode/scene and trusted key required.")
    folder=Path(report_dir).expanduser()
    if not folder.is_absolute() or folder.is_symlink() or not folder.is_dir():
        raise AVImportError("Existing absolute private M37 review directory required.")
    folder=folder.resolve()
    report_path=folder/"signed_av_m28.json"
    obs_path=folder/"observations.json"
    report,report_sha=_read(report_path)
    obs,obs_sha=_read(obs_path)
    m10,tech_sha=_read(m10_report)
    rights,rights_sha=_read(rights_file)
    lineage,lineage_sha=_read(folder/"av_runner_lineage.json")
    if (report.get("schema_version")!=1 or
        report.get("series_id")!=series_id or
        report.get("episode_number")!=episode or
        report.get("scene")!=scene or
        report.get("stage")!="ltx_animate" or
        report.get("publication_approved") is not False or
        report.get("observations_sha256")!=obs_sha or
        report.get("rights_sha256")!=rights_sha or
        report.get("technical_sha256")!=tech_sha or
        obs.get("artifact_sha256")!=report.get("artifact_sha256") or
        obs.get("script_sha256")!=report.get("script_sha256") or
        obs.get("source_voice_sha256")!=m10.get("voice_sha256") or
        m10.get("a2v_sha256")!=report.get("artifact_sha256") or
        m10.get("status")!="AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED" or
        rights.get("artifact_sha256")!=report.get("artifact_sha256") or
        not isinstance(report.get("artifact_sha256"),str) or
        not SHA.fullmatch(report["artifact_sha256"])):
        raise AVImportError("M37 signed media, M10 and rights hashes disagree.")
    signer=report.get("runner_attestation")
    if (not isinstance(signer,dict) or
        set(signer)!={"runner_id","runtime_status","hmac_sha256"} or
        signer["runner_id"]!="m37_synchronized_av_worker" or
        signer["runtime_status"]!="REVIEW_MODELS_EXECUTED" or
        not isinstance(signer["hmac_sha256"],str)):
        raise AVImportError("M37 trusted synchronized-model provenance required.")
    payload={k:v for k,v in report.items() if k!="runner_attestation"}
    canonical=json.dumps(payload,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf-8")
    if not hmac.compare_digest(signer["hmac_sha256"],
                               hmac.new(runner_key,canonical,hashlib.sha256).hexdigest()):
        raise AVImportError("Invalid signed AV runner attestation.")
    roles=report.get("reviewers")
    if (not isinstance(roles,list) or len(roles)!=2 or
        not isinstance(roles[0],dict) or not isinstance(roles[1],dict) or
        roles[0].get("role")!="motion_sync" or
        roles[1].get("role")!="visual_child_safety" or
        roles[0].get("provider_id")==roles[1].get("provider_id")):
        raise AVImportError("Two genuinely distinct reviewer roles required.")
    # The worker's independent model/checkpoint provenance must be signed,
    # with the exact same source and role/model IDs as its M28 judgment.
    sig=lineage.get("runner_hmac_sha256")
    claim={k:v for k,v in lineage.items() if k!="runner_hmac_sha256"}
    encoded=json.dumps(claim,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf-8")
    lineage_reviewers=lineage.get("reviewers")
    if (not isinstance(sig,str) or not SHA.fullmatch(sig) or
        not hmac.compare_digest(sig,hmac.new(
            runner_key,encoded,hashlib.sha256).hexdigest()) or
        lineage.get("schema_version")!=1 or
        lineage.get("mp4_sha256")!=report["artifact_sha256"] or
        lineage.get("wav_sha256")!=obs["source_voice_sha256"] or
        lineage.get("script_sha256")!=report["script_sha256"] or
        lineage.get("m10_sha256")!=tech_sha or
        lineage.get("frame_manifest_sha256")!=obs.get("frame_manifest_sha256") or
        lineage.get("actual_audio_video_models_qualified_by_ci") is not False or
        lineage.get("public_release_authorized") is not False or
        not isinstance(lineage_reviewers,list) or len(lineage_reviewers)!=2):
        raise AVImportError("Signed local AV model/checkpoint lineage absent or modified.")
    for review,pinned in zip(roles,lineage_reviewers):
        if (not isinstance(pinned,dict) or
            set(pinned)!={"role","provider_id","model_id",
                          "binary_sha256","model_sha256"} or
            any(review.get(k)!=pinned.get(k)
                for k in ("role","provider_id","model_id")) or
            any(not isinstance(pinned.get(k),str) or
                not SHA.fullmatch(pinned[k])
                for k in ("binary_sha256","model_sha256"))):
            raise AVImportError("M37 independently pinned model identity mismatch.")
    with queue._connection() as db:
        pause=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
        if not pause or pause["paused"]:
            raise AVImportError("Paused coordinator refuses signed AV import.")
        row=db.execute("""SELECT st.state,st.job_id,st.artifact_sha256,
                    st.source_voice_sha256,st.scene_script_sha256,
                    j.kind,j.state AS job_state,e.state AS episode_state,
                    e.source_sha256,p.episode_script_sha256 AS plan_sha,
                    voice.state AS voice_state,
                    voice.artifact_sha256 AS voice_sha
                FROM studio_scene_stages st
                JOIN jobs j ON j.job_id=st.job_id
                JOIN studio_episodes e ON e.series_id=st.series_id
                    AND e.ordinal=st.ordinal
                JOIN studio_scene_plans p ON p.series_id=st.series_id
                    AND p.ordinal=st.ordinal
                JOIN studio_scene_stages voice ON voice.series_id=st.series_id
                    AND voice.ordinal=st.ordinal AND voice.scene=st.scene
                    AND voice.stage='voice_synthesize'
                WHERE st.series_id=? AND st.ordinal=? AND st.scene=?
                    AND st.stage='ltx_animate'""",
                (series_id,episode,scene)).fetchone()
        if (not row or row["state"] not in ("PENDING_QA","QA_APPROVED") or
            row["job_state"]!="COMPLETED" or row["kind"]!="ltx_animate" or
            row["episode_state"]!="SCRIPT_APPROVED" or
            row["source_sha256"]!=row["plan_sha"] or
            row["voice_state"]!="QA_APPROVED" or
            row["voice_sha"]!=row["source_voice_sha256"] or
            row["voice_sha"]!=obs["source_voice_sha256"] or
            row["job_id"]!=report["job_id"] or
            row["artifact_sha256"]!=report["artifact_sha256"] or
            row["scene_script_sha256"]!=report["script_sha256"]):
            raise AVImportError("Signed AV report does not match current approved Pi media.")
        tech=db.execute("""SELECT report_sha256 FROM studio_scene_audio_checks
            WHERE series_id=? AND ordinal=? AND scene=? AND ltx_job_id=?""",
            (series_id,episode,scene,row["job_id"])).fetchone()
        if tech and tech["report_sha256"]!=tech_sha:
            raise AVImportError("Different M10 already frozen for this LTX job.")
        ai_exists=bool(db.execute("""SELECT 1 FROM sqlite_master WHERE
            type='table' AND name='studio_scene_ai_reviews'""").fetchone())
        prior=(db.execute("""SELECT state,report_sha256 FROM studio_scene_ai_reviews
            WHERE series_id=? AND ordinal=? AND scene=? AND
            stage='ltx_animate' AND job_id=?""",
            (series_id,episode,scene,row["job_id"])).fetchone()
            if ai_exists else None)
        if prior and prior["report_sha256"]!=report_sha:
            raise AVImportError("Prior M28 scene judgment cannot be overwritten.")
        if row["state"]=="QA_APPROVED" and (
                not prior or prior["state"]!="AI_SCENE_READY_PRIVATE_ONLY"
                or not tech):
            raise AVImportError("Previously approved scene has different evidence.")
        if prior and not tech:
            raise AVImportError("Signed M28 report exists without pinned M10.")
        current=row["state"]
    if not execute:
        return {"status":"M37_SIGNED_CURRENT_PI_PREFLIGHT_NO_WRITES",
                "scene":scene,"job_id":report["job_id"],
                "signed_report_sha256":report_sha,"m10_sha256":tech_sha,
                "model_lineage_sha256":lineage_sha,
                "existing_internal_review":bool(prior),
                "actual_models_qualified_by_this_command":False,
                "public_release_authorized":False}
    if current=="QA_APPROVED":
        state="M37_ALREADY_APPROVED_PRIVATE_ONLY"
    else:
        if not tech:
            SceneLedger(queue).register_audio(series_id,episode,scene,m10_report)
        gate=SceneAIGate(queue,attestation_key=runner_key)
        gate.initialize()
        if not prior:
            result=gate.register(series_id,episode,scene,"ltx_animate",
                report_file=report_path,observation_file=obs_path,
                rights_file=rights_file)
            verdict=result["status"]
        else:
            verdict=prior["state"]
        if verdict=="AI_SCENE_READY_PRIVATE_ONLY":
            gate.auto_approve(series_id,episode,scene,"ltx_animate")
            state="M37_AI_LTX_APPROVED_INTERNAL_PRIVATE_ONLY"
        else:
            state="M37_AI_LTX_NEEDS_FIX_PRIVATE_ONLY"
    return {"status":state,"scene":scene,"job_id":report["job_id"],
            "signed_report_sha256":report_sha,"m10_sha256":tech_sha,
            "model_lineage_sha256":lineage_sha,
            "models_executed_by_this_command":False,
            "owner_post_private_video_review_required":True,
            "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-import-synchronized-av")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--series",required=True)
    p.add_argument("--episode",type=int,required=True)
    p.add_argument("--scene",type=int,required=True)
    p.add_argument("--report-dir",type=Path,required=True)
    p.add_argument("--m10-report",type=Path,required=True)
    p.add_argument("--rights",type=Path,required=True)
    p.add_argument("--execute",action="store_true")
    x=p.parse_args(argv)
    try:
        result=import_synchronized(queue=StudioQueue(x.db),
            series_id=x.series,episode=x.episode,scene=x.scene,
            report_dir=x.report_dir,m10_report=x.m10_report,
            rights_file=x.rights,
            runner_key=os.environ.get("KIDS_STUDIO_SCENE_QA_RUNNER_KEY","").encode(),
            execute=x.execute)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (AVImportError,SceneError,QueueError,OSError,ValueError,
            KeyError,TypeError) as exc:
        print("M37_AV_IMPORT_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
