"""M33 bounded private Studio Brain production-cycle driver.

An *explicit* local invocation consumes completed Pi receipts and pre-registered
independent QA proofs. Each step performs at most one durable state change,
never executes a model, imports unverified JSON, uploads, or publishes video.
Mac media and trusted QA workers remain independently authenticated services.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .studio_queue import StudioQueue,QueueError
from .studio_orchestrator import StudioOrchestrator,OrchestrationError,read_plan
from .studio_scenes import SceneLedger,SceneError
from .scene_ai_qa import SceneAIGate,ROLE_CHECKS
from .series_manager import SeriesManager,SeriesError


class CycleError(ValueError):
    pass


HARD_BLOCKERS=frozenset({
    "M32_PLAN_NOT_PINNED_OR_MODIFIED","STUDIO_QUEUE_PAUSED",
    "ACTIVE_EPISODE_MISSING","SOURCE_SCRIPT_CHANGED",
    "SCENE_PLAN_CHANGED","EPISODE_BLOCKED","SCENE_STAGE_SCHEMA_MISSING",
})
ACTIVE_STATES=frozenset({"QUEUED","LEASED"})


class StudioCycle:
    def __init__(self,queue:StudioQueue,plan_file:Path|str):
        self.queue=queue
        self.plan_file=plan_file
        self.orchestrator=StudioOrchestrator(queue)
        self.scenes=SceneLedger(queue)
        self.series=SeriesManager(queue)
        # This gate ONLY auto-approves already registered M28 receipts.
        # It never signs or creates a subjective AI report.
        self.scene_qa=SceneAIGate(queue)

    def status(self)->dict:
        observed=self.orchestrator.status(self.plan_file)
        plan,sha=read_plan(self.plan_file)
        if sha!=observed["plan_sha256"]:
            raise CycleError("Orchestrator plan mutated during observation.")
        sid=plan["series_id"];ordinal=plan["episode_number"]
        external="NO_EXTERNAL_ACTION"
        current_job=None
        current_stage=None
        with self.queue._connection() as db:
            ep=db.execute("""SELECT state,render_job_id FROM studio_episodes
                WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone()
            stages=db.execute("""SELECT scene,stage,state,job_id,
                artifact_sha256,scene_script_sha256 FROM studio_scene_stages
                WHERE series_id=? AND ordinal=? ORDER BY scene,
                CASE stage WHEN 'voice_synthesize' THEN 0 ELSE 1 END""",
                (sid,ordinal)).fetchall()
            for row in stages:
                if row["state"]=="QUEUED":
                    job=db.execute("""SELECT state FROM jobs
                        WHERE job_id=?""",(row["job_id"],)).fetchone()
                    if job and job["state"] in ("COMPLETED","FAILED","CANCELLED"):
                        external="CURRENT_SCENE_RECEIPT_AWAITING_RECONCILIATION"
                    else:
                        external="MAC_MEDIA_WORKER_OR_JOB_ACK_REQUIRED"
                    current_job=row["job_id"]
                    current_stage={"scene":row["scene"],"stage":row["stage"]}
                    break
                if row["state"]=="PENDING_QA":
                    qa=(db.execute("""SELECT state FROM studio_scene_ai_reviews
                        WHERE series_id=? AND ordinal=? AND scene=? AND stage=?
                        AND job_id=?""",
                        (sid,ordinal,row["scene"],row["stage"],
                         row["job_id"])).fetchone()
                        if self._table(db,"studio_scene_ai_reviews") else None)
                    external=("SIGNED_AI_SCENE_REVIEW_ALREADY_RECORDED" if
                              qa and qa["state"]=="AI_SCENE_READY_PRIVATE_ONLY"
                              else "SCENE_REPAIR_PENDING" if
                              qa and qa["state"]=="AI_SCENE_NEEDS_FIX"
                              else "M23_M10_AND_TRUSTED_AI_SCENE_REVIEW_REQUIRED")
                    current_job=row["job_id"]
                    current_stage={"scene":row["scene"],"stage":row["stage"]}
                    break
            if not current_stage and ep and ep["state"]=="RENDER_QUEUED":
                job=db.execute("""SELECT state FROM jobs WHERE job_id=?""",
                    (ep["render_job_id"],)).fetchone()
                external=("FINAL_MASTER_RECEIPT_AWAITING_RECONCILIATION" if
                          job and job["state"] in ("COMPLETED","FAILED","CANCELLED")
                          else "MAC_FINAL_ASSEMBLY_WORKER_REQUIRED")
                current_job=ep["render_job_id"]
            elif not current_stage and ep and ep["state"]=="RENDERED_QA_PENDING":
                external="M7_M27_INDEPENDENT_FINAL_VIDEO_QA_REQUIRED"
            elif not current_stage and ep and ep["state"]=="EPISODE_APPROVED":
                external="AWAIT_SEPARATE_PRIVATE_UPLOAD_POLICY_AND_OWNER_REVIEW"
            elif not current_stage and ep and ep["state"]=="SCRIPT_APPROVED":
                external="OPERATOR_M32_TICK_OR_APPROVED_MAC_RECIPES_REQUIRED"
        return {
            "schema_version":1,
            "status":"M33_OBSERVATION_ONLY_NOT_DEVICE_QUALIFIED",
            "series_id":sid,"episode_number":ordinal,
            "plan_sha256":sha,
            "next_action":observed["next_action"],
            "blockers":observed["blockers"],
            "external_dependency":external,
            "current_job_id":current_job,
            "current_scene_stage":current_stage,
            "mac_pi_hardware_test_ready":False,
            "real_media_production_qualified":False,
            "private_upload_permitted_by_this_tool":False,
            "owner_post_private_review_required":True,
            "public_release_authorized":False,
        }

    @staticmethod
    def _table(db,name):
        return bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name=?""",(name,)).fetchone())

    def step(self,*,execute:bool=False)->dict:
        if type(execute) is not bool:
            raise CycleError("Explicit execute boolean required.")
        status=self.status()
        if not execute:
            return status
        if HARD_BLOCKERS.intersection(status["blockers"]):
            return {"status":"M33_BLOCKED_NO_ACTION",
                "blockers":status["blockers"],
                "external_dependency":status["external_dependency"],
                "public_release_authorized":False}
        sid=status["series_id"];ordinal=status["episode_number"]
        plan,latest_sha=read_plan(self.plan_file)
        if latest_sha!=status["plan_sha256"]:
            return {"status":"M33_BLOCKED_NO_ACTION",
                "blockers":["CURRENT_PLAN_CHANGED"],
                "public_release_authorized":False}
        # Reconciliation is scoped: never repair/advance another show.
        with self.queue._connection() as db:
            ep=db.execute("""SELECT state,render_job_id FROM studio_episodes
                WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone()
            rows=db.execute("""SELECT scene,stage,state,job_id
                FROM studio_scene_stages WHERE series_id=? AND ordinal=?
                ORDER BY scene,CASE stage WHEN 'voice_synthesize' THEN 0 ELSE 1 END""",
                (sid,ordinal)).fetchall()
            completed=False
            for row in rows:
                if row["state"]!="QUEUED":
                    continue
                job=db.execute("SELECT state FROM jobs WHERE job_id=?",
                    (row["job_id"],)).fetchone()
                if job and job["state"] in ("COMPLETED","FAILED","CANCELLED"):
                    completed=True
                    break
            render_ready=False
            if ep and ep["state"]=="RENDER_QUEUED":
                job=db.execute("SELECT state FROM jobs WHERE job_id=?",
                    (ep["render_job_id"],)).fetchone()
                render_ready=bool(job and
                    job["state"] in ("COMPLETED","FAILED","CANCELLED"))
        if completed:
            n=self.scenes.reconcile(sid,ordinal)
            return {"status":"M33_CURRENT_SCENE_RECEIPT_RECONCILED",
                    "updated":n,"public_release_authorized":False}
        if render_ready:
            n=self.series.reconcile(sid,ordinal)
            return {"status":"M33_FINAL_MASTER_RECEIPT_RECONCILED",
                    "updated":n,"public_release_authorized":False}
        # Consume only registered, matched, immutable M28 independent QA.
        # An unsigned or missing report never acquires QA_APPROVED.
        with self.queue._connection() as db:
            ready=[]
            if self._table(db,"studio_scene_ai_reviews"):
                ready=db.execute("""SELECT s.scene,s.stage
                    FROM studio_scene_stages s
                    JOIN studio_scene_ai_reviews a
                      ON a.series_id=s.series_id AND a.ordinal=s.ordinal
                      AND a.scene=s.scene AND a.stage=s.stage AND
                      a.job_id=s.job_id
                    WHERE s.series_id=? AND s.ordinal=?
                      AND s.state='PENDING_QA'
                      AND a.state='AI_SCENE_READY_PRIVATE_ONLY'
                    ORDER BY s.scene,CASE s.stage
                        WHEN 'voice_synthesize' THEN 0 ELSE 1 END""",
                    (sid,ordinal)).fetchall()
        if ready:
            item=ready[0]
            result=self.scene_qa.auto_approve(
                sid,ordinal,item["scene"],item["stage"])
            return {"status":"M33_EXISTING_AI_SCENE_QA_CONSUMED",
                    "scene":item["scene"],"stage":item["stage"],
                    "approval":result["status"],
                    "owner_post_private_video_review_required":True,
                    "public_release_authorized":False}
        # M27 final sign-off is internal only and never a YouTube upload.
        if ep and ep["state"]=="RENDERED_QA_PENDING":
            with self.queue._connection() as db:
                existing=(db.execute("""SELECT 1 FROM studio_ai_final_reviews
                    WHERE series_id=? AND ordinal=? AND render_job_id=?
                    AND status='AI_INTERNAL_READY_PRIVATE_ONLY'""",
                    (sid,ordinal,ep["render_job_id"])).fetchone()
                    if self._table(db,"studio_ai_final_reviews") else None)
            if existing:
                completed=self.series.finalize_ai_private(sid,ordinal)
                return {"status":"M33_INTERNAL_FINAL_READY_PRIVATE_ONLY",
                        "owner_post_private_video_review_required":True,
                        "public_release_authorized":False}
            return {"status":"M33_WAIT_EXTERNAL_QA",
                    "external_dependency":"M7_M27_INDEPENDENT_FINAL_VIDEO_QA_REQUIRED",
                    "public_release_authorized":False}
        # Never reenqueue a leased or QA-pending job. The orchestrator
        # independently checks current plan and the M31 repair budget.
        out=self.orchestrator.tick(self.plan_file)
        if out["status"]=="M32_ONE_PRIVATE_JOB_QUEUED":
            return {"status":"M33_ONE_PRIVATE_JOB_QUEUED",
                    "job_id":out["job_id"],
                    "action":out["action"],
                    "public_release_authorized":False}
        return {"status":"M33_WAIT_FOR_WORKER_OR_REVIEW",
                "next_action":out.get("next_action"),
                "blockers":out.get("blockers",[]),
                "external_dependency":status["external_dependency"],
                "public_release_authorized":False}

    def run_bounded(self,*,steps:int=8,execute:bool=False)->dict:
        if type(steps) is not int or not 1<=steps<=12:
            raise CycleError("Maximum 12 synchronous actions per command.")
        if not execute:
            return self.status()
        results=[]
        for _ in range(steps):
            outcome=self.step(execute=True)
            results.append(outcome)
            # Do not busy-wait for Mac/GPU/AI services; a separate
            # authenticated worker must produce the next durable receipt.
            if outcome["status"] not in (
                    "M33_CURRENT_SCENE_RECEIPT_RECONCILED",
                    "M33_FINAL_MASTER_RECEIPT_RECONCILED",
                    "M33_EXISTING_AI_SCENE_QA_CONSUMED"):
                break
        return {"status":"M33_BOUNDED_CYCLE_STOPPED",
                "steps_executed":len(results),
                "operations":results,
                "external_dependency":self.status()["external_dependency"],
                "mac_pi_hardware_test_ready":False,
                "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="studio-cycle")
    parser.add_argument("--db",type=Path,required=True)
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--steps",type=int,default=8)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=StudioCycle(StudioQueue(args.db),args.plan).run_bounded(
            steps=args.steps,execute=args.execute)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (CycleError,OrchestrationError,SceneError,SeriesError,QueueError,
            ValueError,KeyError,TypeError,OSError) as exc:
        print("M33_CYCLE_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
