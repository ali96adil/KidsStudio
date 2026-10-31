"""M39 honest, read-only two-scene Mac/Pi pilot readiness audit.

The software CI is not hardware proof. This command hashes current private
scene sources, observes existing Pi SQLite and optionally checks Mac engine
bytes; it NEVER signs a QA report, claims a job, calls a model, contacts Pi
over the network, uploads, or asserts pilot authorization. TLS, model quality
and source licensing need separate real owner-device evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .episode_assembly import digest, _ensure_private
from .mac_contract import check_mac_contract, MacIntakeError
from .studio_orchestrator import StudioOrchestrator, OrchestrationError, read_plan
from .studio_queue import StudioQueue, QueueError
from .studio_cycle import StudioCycle, CycleError


class PilotReadinessError(ValueError):
    pass


def _source(path:str|Path,expected:str)->bool:
    if not isinstance(expected,str) or len(expected)!=64:
        return False
    p=Path(path).expanduser()
    if not p.is_absolute() or p.is_symlink() or p.suffix!=".txt":
        return False
    p=p.resolve()
    _ensure_private(p.parent)
    return p.is_file() and 0<p.stat().st_size<=12000 and digest(p)==expected


def audit_pilot(*,queue:StudioQueue,plan_file:Path|str,
                parent_script:Path|str|None=None,
                scene_scripts:tuple[Path|str,Path|str]|None=None,
                mac_contract:Path|str|None=None)->dict:
    """All evidence stays in memory. Missing inputs are never PASS."""
    plan,plan_sha=read_plan(plan_file)
    if (len(plan["scenes"])!=2 or
        [x["scene"] for x in plan["scenes"]]!=[1,2]):
        raise PilotReadinessError("M39 only qualifies a bounded two-scene pilot.")
    sid=plan["series_id"];number=plan["episode_number"]
    observed=StudioOrchestrator(queue).status(plan_file)
    if (observed["series_id"]!=sid or
        observed["episode_number"]!=number or
        observed["plan_sha256"]!=plan_sha):
        raise PilotReadinessError("Orchestrator plan changed during snapshot.")
    snapshot=StudioCycle(queue,plan_file).status()
    gates=[]
    def gate(code,phase,state,detail):
        gates.append({"id":code,"phase":phase,"state":state,"requirement":detail})
    # Source hashes must come from actual private local bytes, NOT an
    # unverified SHA inside a JSON fixture or a stale SQLite receipt.
    if parent_script is None or scene_scripts is None:
        valid_sources=False
        source_state="NOT_SUPPLIED"
    elif (not isinstance(scene_scripts,(tuple,list)) or
          len(scene_scripts)!=2):
        valid_sources=False;source_state="INVALID_SCENE_INPUT"
    else:
        inputs=[(parent_script,plan["script_sha256"])] + [
            (scene_scripts[index],plan["scenes"][index]["script_sha256"])
            for index in range(2)]
        valid_sources=all(_source(path,sha) for path,sha in inputs)
        source_state=("PINNED_BYTES_MATCH" if valid_sources
                      else "HASH_MISMATCH_OR_MISSING")
    gate("LOCAL_SCENE_SOURCE_BYTES","offline",
         "PASS_OFFLINE" if valid_sources else "BLOCKED",
         source_state)
    # The only usable PI pilot start state is a current approved original
    # script and idle queue; no stale/active production jobs may exist.
    current=(observed["next_action"]=="FIRST_AI_VOICE" and
             observed["episode_state"]=="SCRIPT_APPROVED" and
             not observed["blockers"] and
             snapshot["next_action"]=="FIRST_AI_VOICE")
    gate("PI_TWO_SCENE_ORCHESTRATOR","offline",
         "PASS_OFFLINE" if current else "BLOCKED",
         "PINNED_CURRENT_IDLE_FIRST_VOICE" if current else
         "PLAN_OR_QUEUE_NOT_AT_SAFE_PILOT_START")
    with queue._connection() as db:
        current_jobs=db.execute("""SELECT COUNT(*) FROM jobs
            WHERE state IN ('QUEUED','LEASED')""").fetchone()[0]
        paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
    idle=(current_jobs==0 and bool(paused) and paused["paused"]==0)
    gate("STUDIO_IDLE_AND_NOT_PAUSED","offline",
         "PASS_OFFLINE" if idle else "BLOCKED",
         "QUEUE_IDLE" if idle else "PAUSED_OR_OTHER_PENDING_JOBS")
    if mac_contract is None:
        mac_state="NOT_SUPPLIED"
        mac_ok=False
    else:
        try:
            check_mac_contract(mac_contract)
            mac_ok=True
            mac_state="PINNED_FILES_AND_MACHINE_PREREQUISITES_ONLY"
        except (MacIntakeError,OSError,ValueError) as exc:
            mac_ok=False
            mac_state="MAC_CONTRACT_FAILED_"+type(exc).__name__
    gate("OWNER_MAC_MODEL_FILES","offline",
         "PASS_OFFLINE" if mac_ok else "BLOCKED",mac_state)
    # Device/semantics/rights checks cannot be waived by a local fake
    # manifest, CI, arbitrary report JSON or a pre-approved private video.
    for code,phase,detail in (
        ("LIVE_PI_TLS_CLOCK","live_device",
         "M21 authenticated live Pi nonce, fresh clock and current scene"),
        ("MAC_PI_AUTHENTICATED_WORKER","live_device",
         "lease, ACK, media SHA, zero silent failure across actual devices"),
        ("REAL_VOICE_LTX_RENDER","real_inference",
         "original bilingual voice + animation, GPU/MLX execution and exact media"),
        ("REAL_INDEPENDENT_AUDIO_AV_QA","real_inference",
         "qualify M34/M37 audio/AV models on adversarial ground-truth clips"),
        ("RIGHTS_AND_CHILD_POLICY","owner_provenance",
         "document commercial use and independently inspect originals"),
        ("PRIVATE_OAUTH_UPLOAD","post_pilot",
         "separate authorized YouTube PRIVATE-only pilot, no PUBLIC"),
        ("OWNER_POST_PRIVATE_REVIEW","post_pilot",
         "owner reviews uploaded PRIVATE video, accepts/notes/requests changes")
    ):
        gate(code,phase,"NOT_YET_QUALIFIED",detail)
    # The initial device preflight still needs a live M21 check; do not
    # transform offline PASS into authority to lease/render.
    offline_pass=valid_sources and current and idle and mac_ok
    blockers=[x["id"] for x in gates if x["state"]!="PASS_OFFLINE"]
    return {
        "schema_version":1,
        "status":"M39_OFFLINE_PREREQUISITES_MET_LIVE_PILOT_NOT_AUTHORIZED"
                 if offline_pass else "M39_PILOT_READINESS_BLOCKED",
        "series_id":sid,"episode_number":number,
        "plan_sha256":plan_sha,
        "source_hashes_verified":valid_sources,
        "mac_contract_files_checked":mac_ok,
        "offline_gate_count_passed":sum(x["state"]=="PASS_OFFLINE" for x in gates),
        "offline_gate_count_required":4,
        "gates":gates,"blockers":blockers,
        "next_phase":("M21_AUTHENTICATED_LIVE_PI_PREFLIGHT" if offline_pass
                     else "COMPLETE_OFFLINE_LOCAL_PREREQUISITES"),
        "pi_live_contacted":False,"model_inference_performed":False,
        "mac_pi_hardware_qualified":False,
        "actual_model_capability_qualified":False,
        "real_educational_video_created":False,
        "private_upload_permitted":False,
        "owner_post_private_review_required":True,
        "public_release_authorized":False,
        "writes_performed":False,
    }


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-pilot-readiness")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--parent-script",type=Path)
    p.add_argument("--scene-1-script",type=Path)
    p.add_argument("--scene-2-script",type=Path)
    p.add_argument("--mac-contract",type=Path)
    x=p.parse_args(argv)
    try:
        scripts=(x.scene_1_script,x.scene_2_script) if (
            x.scene_1_script is not None and
            x.scene_2_script is not None) else None
        report=audit_pilot(queue=StudioQueue(x.db),plan_file=x.plan,
            parent_script=x.parent_script,scene_scripts=scripts,
            mac_contract=x.mac_contract)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report["status"].startswith(
            "M39_OFFLINE_PREREQUISITES_MET") else 1
    except (PilotReadinessError,OrchestrationError,CycleError,QueueError,
            OSError,ValueError,KeyError,TypeError) as exc:
        print("M39_READINESS_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
