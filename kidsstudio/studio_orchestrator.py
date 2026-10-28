"""M32 conservative one-command Studio Brain coordinator, PRIVATE-only.

It observes real SQLite stage/QA receipts, schedules at most one *already
approved* job each tick, and never executes a model, renders, exports assets
or contacts YouTube. All Mac recipes and source checks remain the media
worker's responsibility; never declare hardware or PUBLIC readiness based
on a synthetic pipeline test. No owner stage approvals are fabricated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from .episode_assembly import digest, _ensure_private
from .series_manager import SeriesManager, SeriesError
from .studio_scenes import SceneLedger, SceneError, ID, SHA, RECIPE
from .scene_repair import SceneRepair, RepairError
from .studio_queue import StudioQueue, QueueError

class OrchestrationError(ValueError):
    pass

def read_plan(file: str|Path)->tuple[dict,str]:
    candidate=Path(file).expanduser()
    if (not candidate.is_absolute() or candidate.is_symlink() or
        candidate.suffix.lower()!=".json"):
        raise OrchestrationError("M32 plan must be private absolute JSON, not symlink.")
    path=candidate.resolve()
    _ensure_private(path.parent)
    if not path.is_file() or not 30<=path.stat().st_size<=25000:
        raise OrchestrationError("Missing or oversized operator plan.")
    try: plan=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError,UnicodeError) as exc:
        raise OrchestrationError("Malformed M32 plan JSON.") from exc
    fields={"schema_version","series_id","episode_number","script_sha256",
            "scene_plan_sha256","scenes","assembly",
            "public_release_authorized"}
    if (not isinstance(plan,dict) or set(plan)!=fields or
        type(plan["schema_version"]) is not int or plan["schema_version"]!=1 or
        not isinstance(plan["series_id"],str) or not ID.fullmatch(plan["series_id"]) or
        type(plan["episode_number"]) is not int or
        not 1<=plan["episode_number"]<=120 or
        any(not isinstance(plan[x],str) or not SHA.fullmatch(plan[x])
            for x in ("script_sha256","scene_plan_sha256")) or
        plan["public_release_authorized"] is not False):
        raise OrchestrationError("Unsafe identity or source hash in M32 plan.")
    scenes=plan["scenes"]
    if (not isinstance(scenes,list) or not 2<=len(scenes)<=40):
        raise OrchestrationError("M32 expects 2–40 ordered pinned scenes.")
    for i,s in enumerate(scenes,1):
        if (not isinstance(s,dict) or set(s)!={"scene","script_sha256",
              "voice_recipe","ltx_recipe"} or
            type(s["scene"]) is not int or s["scene"]!=i or
            not isinstance(s["script_sha256"],str) or
            not SHA.fullmatch(s["script_sha256"]) or
            any(not isinstance(s[k],str) or not RECIPE.fullmatch(s[k])
                for k in ("voice_recipe","ltx_recipe"))):
            raise OrchestrationError("Current ordered scene/recipe pins required.")
    assembly=plan["assembly"]
    if (not isinstance(assembly,dict) or
        set(assembly)!={"recipe_id","catalogue_sha256"} or
        not isinstance(assembly["recipe_id"],str) or
        not RECIPE.fullmatch(assembly["recipe_id"]) or
        not isinstance(assembly["catalogue_sha256"],str) or
        not SHA.fullmatch(assembly["catalogue_sha256"])):
        raise OrchestrationError("Exact private final-montage recipe/catalogue required.")
    return plan,digest(path)

def _has(db,table:str)->bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (table,)).fetchone())

class StudioOrchestrator:
    def __init__(self,queue:StudioQueue):
        self.queue=queue
        self.series=SeriesManager(queue)
        self.scenes=SceneLedger(queue)
        self.repair=SceneRepair(queue)

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_orchestrator_plans(
                series_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                plan_sha256 TEXT NOT NULL,script_sha256 TEXT NOT NULL,
                scene_plan_sha256 TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal),
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_episodes(series_id,ordinal)
            )""")

    def pin(self,filename:str|Path)->dict:
        plan,plan_sha=read_plan(filename)
        sid=plan["series_id"];num=plan["episode_number"]
        with self.queue._connection(write=True) as db:
            if not _has(db,"studio_scenes"):
                raise OrchestrationError("M13 scene ledger must be initialized.")
            ep=db.execute("""SELECT e.state,e.source_sha256,
                s.state AS series_state FROM studio_episodes e
                JOIN studio_series s ON s.series_id=e.series_id
                WHERE e.series_id=? AND e.ordinal=?""",(sid,num)).fetchone()
            parent=db.execute("""SELECT plan_sha256,episode_script_sha256
                FROM studio_scene_plans WHERE series_id=? AND ordinal=?""",
                (sid,num)).fetchone()
            children=db.execute("""SELECT scene,script_sha256
                FROM studio_scenes WHERE series_id=? AND ordinal=?
                ORDER BY scene""",(sid,num)).fetchall()
            if (not ep or ep["state"]!="SCRIPT_APPROVED" or
                ep["series_state"]!="ACTIVE" or
                ep["source_sha256"]!=plan["script_sha256"] or
                not parent or parent["plan_sha256"]!=plan["scene_plan_sha256"] or
                parent["episode_script_sha256"]!=plan["script_sha256"] or
                len(children)!=len(plan["scenes"]) or
                any(c["scene"]!=p["scene"] or
                    c["script_sha256"]!=p["script_sha256"]
                    for c,p in zip(children,plan["scenes"]))):
                raise OrchestrationError("No current approved episode and exact immutable scene plan.")
            if db.execute("""SELECT 1 FROM studio_orchestrator_plans
                WHERE series_id=? AND ordinal=?""",(sid,num)).fetchone():
                raise OrchestrationError("M32 orchestration plan immutable; no overwrite.")
            db.execute("""INSERT INTO studio_orchestrator_plans VALUES
                (?,?,?,?,?,?)""",(sid,num,plan_sha,plan["script_sha256"],
                 plan["scene_plan_sha256"],self.queue.clock()))
        return {"status":"M32_PRIVATE_PLAN_PINNED_NO_JOBS_QUEUED",
                "plan_sha256":plan_sha,
                "public_release_authorized":False}

    @staticmethod
    def _repair_available(db,sid:str,num:int,scene:int,stage:str,receipt)->bool:
        """Read-only narrow check; actual dispatch repeats all M31 guards."""
        if not (receipt and receipt["state"]=="PENDING_QA" and
                _has(db,"studio_scene_ai_reviews") and
                _has(db,"studio_scene_repair_plans") and
                _has(db,"studio_scene_repair_attempts")):
            return False
        qa=db.execute("""SELECT state,technical_sha256,
                artifact_sha256,script_sha256,report_sha256,
                first_provider,second_provider
            FROM studio_scene_ai_reviews WHERE
            series_id=? AND ordinal=? AND scene=? AND stage=? AND
            job_id=?""",(sid,num,scene,stage,receipt["job_id"])).fetchone()
        plan=db.execute("""SELECT recipes_json,script_sha256 FROM studio_scene_repair_plans
            WHERE series_id=? AND ordinal=? AND scene=? AND stage=?""",
            (sid,num,scene,stage)).fetchone()
        if (not qa or qa["state"]!="AI_SCENE_NEEDS_FIX" or not plan or
            qa["artifact_sha256"]!=receipt["artifact_sha256"] or
            qa["script_sha256"]!=receipt["scene_script_sha256"] or
            plan["script_sha256"]!=receipt["scene_script_sha256"] or
            qa["first_provider"]==qa["second_provider"] or
            not isinstance(qa["report_sha256"],str) or
            not SHA.fullmatch(qa["report_sha256"])):
            return False
        try:budget=len(json.loads(plan["recipes_json"]))
        except (TypeError,ValueError):return False
        used=db.execute("""SELECT COUNT(*) FROM studio_scene_repair_attempts
            WHERE series_id=? AND ordinal=? AND scene=? AND stage=?""",
            (sid,num,scene,stage)).fetchone()[0]
        if used>=min(2,budget):
            return False
        if stage=="voice_synthesize":
            if db.execute("""SELECT 1 FROM studio_scene_stages WHERE
                series_id=? AND ordinal=? AND scene=?
                AND stage='ltx_animate'""",(sid,num,scene)).fetchone():
                return False
            tech=db.execute("""SELECT report_sha256 FROM
                studio_scene_voice_checks WHERE series_id=? AND ordinal=?
                AND scene=? AND voice_job_id=?""",
                (sid,num,scene,receipt["job_id"])).fetchone()
        else:
            tech=db.execute("""SELECT report_sha256 FROM
                studio_scene_audio_checks WHERE series_id=? AND ordinal=?
                AND scene=? AND ltx_job_id=?""",
                (sid,num,scene,receipt["job_id"])).fetchone()
        return bool(tech and tech["report_sha256"]==qa["technical_sha256"])

    def status(self,filename:str|Path)->dict:
        plan,sha=read_plan(filename)
        sid=plan["series_id"];num=plan["episode_number"]
        blockers=[]
        scene_status=[]
        next_action="NO_ACTION"
        with self.queue._connection() as db:
            pinned=(db.execute("""SELECT * FROM studio_orchestrator_plans
                WHERE series_id=? AND ordinal=?""",(sid,num)).fetchone()
                if _has(db,"studio_orchestrator_plans") else None)
            if (not pinned or pinned["plan_sha256"]!=sha or
                pinned["script_sha256"]!=plan["script_sha256"] or
                pinned["scene_plan_sha256"]!=plan["scene_plan_sha256"]):
                blockers.append("M32_PLAN_NOT_PINNED_OR_MODIFIED")
            pause=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
            if not pause or pause["paused"]:
                blockers.append("STUDIO_QUEUE_PAUSED")
            ep=db.execute("""SELECT e.*,s.state AS series_state
                FROM studio_episodes e JOIN studio_series s
                  ON e.series_id=s.series_id
                WHERE e.series_id=? AND e.ordinal=?""",(sid,num)).fetchone()
            if not ep or ep["series_state"]!="ACTIVE":
                blockers.append("ACTIVE_EPISODE_MISSING")
            elif ep["source_sha256"]!=plan["script_sha256"]:
                blockers.append("SOURCE_SCRIPT_CHANGED")
            elif ep["state"]=="BLOCKED":
                blockers.append("EPISODE_BLOCKED")
            if not _has(db,"studio_scene_stages"):
                blockers.append("SCENE_STAGE_SCHEMA_MISSING")
                stage_rows=[]
            else:
                stage_rows=db.execute("""SELECT scene,stage,state,job_id,
                    artifact_sha256,source_voice_sha256,scene_script_sha256
                    FROM studio_scene_stages WHERE series_id=? AND ordinal=?""",
                    (sid,num)).fetchall()
            rows={(r["scene"],r["stage"]):r for r in stage_rows}
            pending=None
            if ep and ep["state"]=="SCRIPT_APPROVED":
                scene_plan=(db.execute("""SELECT plan_sha256,episode_script_sha256
                    FROM studio_scene_plans WHERE series_id=? AND ordinal=?""",
                    (sid,num)).fetchone() if _has(db,"studio_scene_plans") else None)
                if (not scene_plan or
                    scene_plan["plan_sha256"]!=plan["scene_plan_sha256"] or
                    scene_plan["episode_script_sha256"]!=plan["script_sha256"]):
                    blockers.append("SCENE_PLAN_CHANGED")
                for item in plan["scenes"]:
                    index=item["scene"]
                    voice=rows.get((index,"voice_synthesize"))
                    ltx=rows.get((index,"ltx_animate"))
                    state={"scene":index,
                           "voice":voice["state"] if voice else "NOT_QUEUED",
                           "ltx":ltx["state"] if ltx else "NOT_QUEUED"}
                    scene_status.append(state)
                    if pending is not None:
                        continue
                    if index==1 and not voice:
                        if len(plan["scenes"])!=2 or not _has(db,"studio_script_ai_reviews"):
                            pending=("BLOCK","FIRST_VOICE_REQUIRES_AI_SCRIPT_GATE")
                        else:
                            ai=db.execute("""SELECT 1 FROM studio_script_ai_reviews
                                WHERE series_id=? AND ordinal=? AND
                                    original_sha256=? AND
                                    verdict='AI_SCRIPT_PRIVATE_READY' AND
                                    first_provider!=second_provider AND
                                    revision=?""",
                                (sid,num,plan["script_sha256"],ep["revision"])).fetchone()
                            pending=(("QUEUE","FIRST_AI_VOICE") if ai
                                     else ("BLOCK","FIRST_VOICE_REQUIRES_AI_SCRIPT_GATE"))
                    elif not voice:
                        previous=rows.get((index-1,"ltx_animate"))
                        pending=(("QUEUE","NEXT_VOICE") if previous and
                                 previous["state"]=="QA_APPROVED" else
                                 ("BLOCK","PREVIOUS_SCENE_NOT_APPROVED"))
                    elif voice["state"]!="QA_APPROVED":
                        pending=(("REPAIR","REPAIR_REJECTED_SCENE") if
                            self._repair_available(db,sid,num,index,
                                "voice_synthesize",voice) else
                            ("BLOCK","SCENE_VOICE_"+voice["state"]))
                    elif not ltx:
                        pending=("QUEUE","NEXT_LTX")
                    elif ltx["state"]!="QA_APPROVED":
                        pending=(("REPAIR","REPAIR_REJECTED_SCENE") if
                            self._repair_available(db,sid,num,index,
                                "ltx_animate",ltx) else
                            ("BLOCK","SCENE_LTX_"+ltx["state"]))
                if pending is None and scene_status:
                    pending=("QUEUE","ASSEMBLE_FINAL_EPISODE")
            elif ep:
                pending=("BLOCK","EPISODE_"+ep["state"])
            if pending:
                next_action=pending[1]
                if pending[0]=="BLOCK":
                    blockers.append(next_action)
            if "M32_PLAN_NOT_PINNED_OR_MODIFIED" in blockers:
                next_action="PIN_CURRENT_PLAN"
            elif "STUDIO_QUEUE_PAUSED" in blockers:
                next_action="PAUSED"
            elif any(x in blockers for x in ("SOURCE_SCRIPT_CHANGED",
                                             "SCENE_PLAN_CHANGED",
                                             "ACTIVE_EPISODE_MISSING")):
                next_action="STOP_AND_RECONCILE"
        return {"schema_version":1,"status":"M32_OBSERVED_NOT_HARDWARE_QUALIFIED",
                "series_id":sid,"episode_number":num,
                "plan_sha256":sha,
                "episode_state":ep["state"] if ep else "MISSING",
                "next_action":next_action,"blockers":list(dict.fromkeys(blockers)),
                "scenes":scene_status,
                "synthetic_ci_is_not_hardware_qualification":True,
                "software_full_cycle_qualified":False,
                "mac_pi_hardware_test_ready":False,
                "youtube_private_upload_qualified":False,
                "owner_final_video_review_required":True,
                "unqualified_external_checks":[
                    "real_multimodal_audio_child_safety_models",
                    "source_rights_proof_external_validation",
                    "mac_pi_production_link_and_rendered_original_video",
                    "real_private_youtube_oauth_and_owner_post_upload_review"
                ],
                "public_release_authorized":False}

    def tick(self,filename:str|Path)->dict:
        """At most one safe queue action. Never calls video/audio/model APIs."""
        snapshot=self.status(filename)
        if snapshot["blockers"]:
            return {"status":"M32_BLOCKED_NO_JOB_QUEUED",
                    "next_action":snapshot["next_action"],
                    "blockers":snapshot["blockers"],
                    "public_release_authorized":False}
        action=snapshot["next_action"]
        plan,current_sha=read_plan(filename)
        if current_sha!=snapshot["plan_sha256"]:
            return {"status":"M32_BLOCKED_NO_JOB_QUEUED",
                    "next_action":"PLAN_CHANGED_DURING_TICK",
                    "blockers":["M32_PLAN_RACE"],
                    "public_release_authorized":False}
        sid=plan["series_id"];num=plan["episode_number"]
        if action=="REPAIR_REJECTED_SCENE":
            result=self.repair.run_once(series_id=sid,ordinal=num)
            if result["status"]!="M31_BOUNDED_SCENE_REPAIR_QUEUED":
                return {"status":"M32_BLOCKED_NO_JOB_QUEUED",
                        "next_action":"REPAIR_PLAN_INELIGIBLE",
                        "blockers":["M31_REPAIR_FENCED"],
                        "public_release_authorized":False}
            return {"status":"M32_ONE_PRIVATE_JOB_QUEUED",
                    "job_id":result["new_job_id"],
                    "action":"REPAIR_REJECTED_SCENE",
                    "repair_attempt":result["repair_attempt"],
                    "public_release_authorized":False}
        if action=="FIRST_AI_VOICE":
            job=self.scenes.queue_first_voice_ai(
                sid,num,plan["scenes"][0]["voice_recipe"],
                plan["scene_plan_sha256"])
        elif action in ("NEXT_VOICE","NEXT_LTX"):
            pending=next(x for x in snapshot["scenes"]
                         if x["voice"]=="NOT_QUEUED" or
                            (x["voice"]=="QA_APPROVED" and
                             x["ltx"]=="NOT_QUEUED"))
            i=pending["scene"]
            item=plan["scenes"][i-1]
            stage="voice_synthesize" if action=="NEXT_VOICE" else "ltx_animate"
            job=self.scenes.queue_stage(sid,num,i,stage,
                    item["voice_recipe"] if action=="NEXT_VOICE"
                    else item["ltx_recipe"])
        elif action=="ASSEMBLE_FINAL_EPISODE":
            job=self.series.queue_render(sid,num,
                plan["assembly"]["recipe_id"],media_kind="episode_assemble",
                catalogue_sha256=plan["assembly"]["catalogue_sha256"])
        else:
            return {"status":"M32_NO_APPROVED_AUTOMATED_ACTION",
                    "next_action":action,
                    "public_release_authorized":False}
        return {"status":"M32_ONE_PRIVATE_JOB_QUEUED",
                "job_id":job,"action":action,
                "public_release_authorized":False}

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-orchestrator")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--plan",type=Path)
    p.add_argument("command",choices=["init","pin","status","tick"])
    args=p.parse_args(argv)
    try:
        q=StudioQueue(args.db)
        coord=StudioOrchestrator(q)
        if args.command=="init":
            coord.initialize()
            result={"status":"M32_ORCHESTRATOR_LEDGER_INITIALIZED",
                    "public_release_authorized":False}
        else:
            if args.plan is None:
                raise OrchestrationError("Private --plan required.")
            result=(coord.pin(args.plan) if args.command=="pin" else
                    coord.status(args.plan) if args.command=="status" else
                    coord.tick(args.plan))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result["status"]!="M32_BLOCKED_NO_JOB_QUEUED" else 1
    except (OrchestrationError,SceneError,SeriesError,RepairError,QueueError,
            OSError,ValueError,TypeError,KeyError) as exc:
        print("M32_ORCHESTRATOR_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
