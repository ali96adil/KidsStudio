"""M31 bounded, per-scene repair scheduling from negative independent AI QA.

No speculative retries: ONLY exact current, completed job + current M28
AI_SCENE_NEEDS_FIX evidence may trigger a new job, under an immutable
pre-approved private recipe plan (at most two repairs). Never retry a
lost/leased/ambiguous job, accepted asset, or already started montage.
Accepted voices and unrelated scenes are never changed. No PUBLIC paths.

This coordinator ONLY queues safe pinned recipe identifiers; the Mac media
worker still validates every actual model recipe and its local catalogue.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from uuid import uuid4

from .episode_assembly import digest, _ensure_private
from .studio_queue import StudioQueue, _json_object
from .studio_scenes import ID, SHA, RECIPE, STAGES

MAX_REPAIRS=2


class RepairError(ValueError):
    pass


def _load_plan(filename:str|Path)->tuple[dict,str]:
    p=Path(filename).expanduser()
    if not p.is_absolute() or p.is_symlink() or p.suffix.lower()!=".json":
        raise RepairError("Absolute private non-symlink repair plan required.")
    p=p.resolve()
    _ensure_private(p.parent)
    if not p.is_file() or not 10<=p.stat().st_size<=10000:
        raise RepairError("Missing or oversized repair plan.")
    try:doc=json.loads(p.read_text(encoding="utf-8"))
    except (ValueError,UnicodeError,OSError) as exc:
        raise RepairError("Malformed repair plan.") from exc
    fields={"schema_version","series_id","episode_number","scene","stage",
            "script_sha256","recipes","public_release_authorized"}
    if (not isinstance(doc,dict) or set(doc)!=fields or
        type(doc["schema_version"]) is not int or doc["schema_version"]!=1 or
        not isinstance(doc["series_id"],str) or not ID.fullmatch(doc["series_id"]) or
        type(doc["episode_number"]) is not int or not 1<=doc["episode_number"]<=120 or
        type(doc["scene"]) is not int or not 1<=doc["scene"]<=40 or
        doc["stage"] not in STAGES or
        not isinstance(doc["script_sha256"],str) or
        not SHA.fullmatch(doc["script_sha256"]) or
        not isinstance(doc["recipes"],list) or
        not 1<=len(doc["recipes"])<=MAX_REPAIRS or
        any(not isinstance(x,str) or not RECIPE.fullmatch(x) for x in doc["recipes"]) or
        len(set(doc["recipes"]))!=len(doc["recipes"]) or
        doc["public_release_authorized"] is not False):
        raise RepairError("Repair plan must pin current scene, stage, 1–2 recipes and no PUBLIC.")
    return doc,digest(p)


class SceneRepair:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_scene_repair_plans(
                series_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                scene INTEGER NOT NULL,stage TEXT NOT NULL,
                script_sha256 TEXT NOT NULL,recipes_json TEXT NOT NULL,
                plan_sha256 TEXT NOT NULL,created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,scene,stage),
                FOREIGN KEY(series_id,ordinal,scene)
                REFERENCES studio_scenes(series_id,ordinal,scene)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_scene_repair_attempts(
                series_id TEXT NOT NULL,ordinal INTEGER NOT NULL,
                scene INTEGER NOT NULL,stage TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                prior_job_id TEXT NOT NULL,
                prior_artifact_sha256 TEXT NOT NULL,
                failed_ai_report_sha256 TEXT NOT NULL,
                new_job_id TEXT NOT NULL UNIQUE,
                new_recipe_id TEXT NOT NULL,
                plan_sha256 TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,scene,stage,attempt),
                UNIQUE(prior_job_id),
                FOREIGN KEY(series_id,ordinal,scene)
                REFERENCES studio_scenes(series_id,ordinal,scene)
            )""")

    def register_plan(self,filename:str|Path)->dict:
        doc,plan_sha=_load_plan(filename)
        sid=doc["series_id"];ordinal=doc["episode_number"];scene=doc["scene"]
        stage=doc["stage"];source=doc["script_sha256"]
        with self.queue._connection(write=True) as db:
            ep=db.execute("""SELECT e.state,e.source_sha256,
                s.state AS series_state,p.episode_script_sha256,
                sc.script_sha256
                FROM studio_episodes e
                JOIN studio_series s ON s.series_id=e.series_id
                JOIN studio_scene_plans p ON p.series_id=e.series_id
                    AND p.ordinal=e.ordinal
                JOIN studio_scenes sc ON sc.series_id=e.series_id
                    AND sc.ordinal=e.ordinal AND sc.scene=?
                WHERE e.series_id=? AND e.ordinal=?""",
                (scene,sid,ordinal)).fetchone()
            row=db.execute("""SELECT state,job_id FROM studio_scene_stages
                WHERE series_id=? AND ordinal=? AND scene=? AND stage=?""",
                (sid,ordinal,scene,stage)).fetchone()
            if (not ep or ep["state"]!="SCRIPT_APPROVED" or
                ep["series_state"]!="ACTIVE" or
                ep["episode_script_sha256"]!=ep["source_sha256"] or
                ep["script_sha256"]!=source or
                not row or row["state"]!="PENDING_QA"):
                raise RepairError("Only current active, rendered scene QA can acquire a repair plan.")
            existing=db.execute("""SELECT 1 FROM studio_scene_repair_plans
                WHERE series_id=? AND ordinal=? AND scene=? AND stage=?""",
                (sid,ordinal,scene,stage)).fetchone()
            if existing:
                raise RepairError("Repair plan is immutable; no replacement or expansion.")
            current=db.execute("SELECT payload FROM jobs WHERE job_id=?",
                               (row["job_id"],)).fetchone()
            if not current:
                raise RepairError("Current source job missing.")
            try:old_recipe=json.loads(current["payload"])["recipe_id"]
            except (TypeError,ValueError,KeyError) as exc:
                raise RepairError("Current recipe provenance missing.") from exc
            if old_recipe in doc["recipes"]:
                raise RepairError("Repair recipes must differ from original failed recipe.")
            db.execute("""INSERT INTO studio_scene_repair_plans VALUES
                (?,?,?,?,?,?,?,?)""",
                (sid,ordinal,scene,stage,source,
                 json.dumps(doc["recipes"],separators=(",",":")),
                 plan_sha,self.queue.clock()))
        return {"status":"M31_REPAIR_PLAN_PINNED_NOT_EXECUTED",
                "plan_sha256":plan_sha,"max_repairs":len(doc["recipes"]),
                "owner_post_private_review_required":True,
                "public_release_authorized":False}

    def _try_one(self,db,row)->dict|None:
        sid=row["series_id"];ordinal=row["ordinal"];scene=row["scene"]
        stage=row["stage"];script=row["scene_script_sha256"]
        if row["state"]!="PENDING_QA":
            return None
        ep=db.execute("""SELECT e.state,e.source_sha256,
            s.state AS series_state,p.episode_script_sha256,
            sc.script_sha256 AS current_scene_script
            FROM studio_episodes e JOIN studio_series s
                ON s.series_id=e.series_id
            JOIN studio_scene_plans p ON p.series_id=e.series_id
                AND p.ordinal=e.ordinal
            JOIN studio_scenes sc ON sc.series_id=e.series_id AND
                sc.ordinal=e.ordinal AND sc.scene=?
            WHERE e.series_id=? AND e.ordinal=?""",
            (scene,sid,ordinal)).fetchone()
        if (not ep or ep["state"]!="SCRIPT_APPROVED" or
            ep["series_state"]!="ACTIVE" or
            ep["episode_script_sha256"]!=ep["source_sha256"] or
            ep["current_scene_script"]!=script):
            return None
        plan=db.execute("""SELECT * FROM studio_scene_repair_plans
            WHERE series_id=? AND ordinal=? AND scene=? AND stage=?""",
            (sid,ordinal,scene,stage)).fetchone()
        if not plan or plan["script_sha256"]!=script:
            return None
        recipes=json.loads(plan["recipes_json"])
        prior=db.execute("""SELECT attempt,new_recipe_id FROM
            studio_scene_repair_attempts WHERE series_id=? AND ordinal=?
            AND scene=? AND stage=? ORDER BY attempt""",
            (sid,ordinal,scene,stage)).fetchall()
        next_attempt=len(prior)+1
        if next_attempt>len(recipes) or next_attempt>MAX_REPAIRS:
            return None
        if len(prior)>0 and [r["attempt"] for r in prior]!=list(range(1,next_attempt)):
            raise RepairError("Repair generation history corrupted.")
        candidate=recipes[next_attempt-1]
        if any(r["new_recipe_id"]==candidate for r in prior):
            raise RepairError("Already executed repair recipe.")
        qa=db.execute("""SELECT * FROM studio_scene_ai_reviews WHERE
            series_id=? AND ordinal=? AND scene=? AND stage=?
            AND job_id=? AND state='AI_SCENE_NEEDS_FIX'""",
            (sid,ordinal,scene,stage,row["job_id"])).fetchone()
        if (not qa or qa["script_sha256"]!=script or
            qa["artifact_sha256"]!=row["artifact_sha256"] or
            qa["first_provider"]==qa["second_provider"] or
            not isinstance(qa["report_sha256"],str) or
            not SHA.fullmatch(qa["report_sha256"])):
            return None
        old=db.execute("""SELECT kind,state,payload,result_json
            FROM jobs WHERE job_id=?""",(row["job_id"],)).fetchone()
        if not old or old["kind"]!=stage or old["state"]!="COMPLETED":
            return None
        try:
            original=json.loads(old["payload"]);receipt=json.loads(old["result_json"])
        except (TypeError,ValueError) as exc:
            raise RepairError("Existing media receipt malformed.") from exc
        status,media_type=STAGES[stage]
        if (receipt.get("status")!=status or
            receipt.get("artifact_type")!=media_type or
            receipt.get("artifact_sha256")!=row["artifact_sha256"] or
            receipt.get("publication_approved") is not False or
            original.get("script_sha256")!=script or
            original.get("recipe_id")==candidate):
            return None
        new_payload={"recipe_id":candidate,"script_sha256":script}
        if stage=="voice_synthesize":
            # Never mutate voice once any downstream animation exists,
            # including queued/leased and independently accepted clips.
            downstream=db.execute("""SELECT 1 FROM studio_scene_stages
                WHERE series_id=? AND ordinal=? AND scene=?
                AND stage='ltx_animate'""",(sid,ordinal,scene)).fetchone()
            if downstream:
                return None
            checked=db.execute("""SELECT report_sha256
                FROM studio_scene_voice_checks
                WHERE series_id=? AND ordinal=? AND scene=?
                AND voice_job_id=? AND voice_sha256=?
                AND status='TECH_PASS_OWNER_LISTENING_PENDING'""",
                (sid,ordinal,scene,row["job_id"],row["artifact_sha256"])).fetchone()
            if (not checked or checked["report_sha256"]!=qa["technical_sha256"]
                or "voice_sha256" in original):
                return None
        else:
            voice=db.execute("""SELECT * FROM studio_scene_stages
                WHERE series_id=? AND ordinal=? AND scene=?
                AND stage='voice_synthesize'""",
                (sid,ordinal,scene)).fetchone()
            if (not voice or voice["state"]!="QA_APPROVED" or
                voice["scene_script_sha256"]!=script or
                not isinstance(voice["artifact_sha256"],str) or
                not SHA.fullmatch(voice["artifact_sha256"]) or
                row["source_voice_sha256"]!=voice["artifact_sha256"] or
                original.get("voice_sha256")!=voice["artifact_sha256"]):
                return None
            audio=db.execute("""SELECT report_sha256
                FROM studio_scene_audio_checks
                WHERE series_id=? AND ordinal=? AND scene=?
                AND ltx_job_id=? AND voice_sha256=?
                AND a2v_sha256=?
                AND status='TECH_COMPATIBLE_HUMAN_QA_REQUIRED'""",
                (sid,ordinal,scene,row["job_id"],
                 voice["artifact_sha256"],row["artifact_sha256"])).fetchone()
            if not audio or audio["report_sha256"]!=qa["technical_sha256"]:
                return None
            new_payload["voice_sha256"]=voice["artifact_sha256"]
        key=(f"scene:{sid}:episode:{ordinal}:s{scene}:{stage}:"
             f"repair{next_attempt}:{script[:12]}")
        packed=_json_object(new_payload,"repair_payload")
        if db.execute("SELECT 1 FROM jobs WHERE request_key=?",(key,)).fetchone():
            raise RepairError("Repair job key collision; manual reconciliation required.")
        new_job=uuid4().hex
        now=self.queue.clock()
        db.execute("""INSERT INTO jobs
            (job_id,request_key,kind,payload,state,max_attempts,
             available_at,created_at,updated_at)
             VALUES (?,?,?,?,?,?,?,?,?)""",
            (new_job,key,stage,packed,"QUEUED",1,now,now,now))
        self.queue._event(db,new_job,"ENQUEUED",{"kind":stage,"repair":next_attempt})
        db.execute("""INSERT INTO studio_scene_repair_attempts VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid,ordinal,scene,stage,next_attempt,row["job_id"],
             row["artifact_sha256"],qa["report_sha256"],
             new_job,candidate,plan["plan_sha256"],now))
        db.execute("""UPDATE studio_scene_stages SET state='QUEUED',
            job_id=?,artifact_sha256=NULL,owner_note=NULL,updated_at=?
            WHERE series_id=? AND ordinal=? AND scene=? AND stage=?
            AND job_id=? AND state='PENDING_QA'""",
            (new_job,now,sid,ordinal,scene,stage,row["job_id"]))
        db.execute("""INSERT INTO studio_series_notes
            (series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
            (sid,ordinal,("M31: repair "+str(next_attempt)+" for scene "+
                str(scene)+" "+stage+" from signed negative AI QA "+qa["report_sha256"][:12]),
             now))
        return {"status":"M31_BOUNDED_SCENE_REPAIR_QUEUED",
                "series_id":sid,"episode_number":ordinal,
                "scene":scene,"stage":stage,"repair_attempt":next_attempt,
                "max_repairs":len(recipes),"previous_job_id":row["job_id"],
                "new_job_id":new_job,"new_recipe_id":candidate,
                "retained_other_scenes":True,"public_release_authorized":False}

    def run_once(self)->dict:
        """Atomically consider current negative AI scenes, queue at most one."""
        with self.queue._connection(write=True) as db:
            pause=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
            if not pause or pause["paused"]:
                return {"status":"M31_PAUSED_NO_REPAIR","public_release_authorized":False}
            rows=db.execute("""SELECT s.* FROM studio_scene_stages s
                JOIN studio_scene_repair_plans p ON
                  p.series_id=s.series_id AND p.ordinal=s.ordinal AND
                  p.scene=s.scene AND p.stage=s.stage
                WHERE s.state='PENDING_QA'
                ORDER BY s.series_id,s.ordinal,s.scene,
                CASE s.stage WHEN 'voice_synthesize' THEN 0 ELSE 1 END""").fetchall()
            for row in rows:
                result=self._try_one(db,row)
                if result is not None:
                    return result
        return {"status":"M31_NO_ELIGIBLE_REPAIRS",
                "public_release_authorized":False}

    def snapshot(self)->dict:
        with self.queue._connection() as db:
            rows=db.execute("""SELECT p.series_id,p.ordinal,p.scene,p.stage,
                p.plan_sha256,s.state AS scene_state,s.job_id,
                s.artifact_sha256,
                COUNT(a.attempt) AS attempts_used
                FROM studio_scene_repair_plans p
                JOIN studio_scene_stages s ON s.series_id=p.series_id
                  AND s.ordinal=p.ordinal AND s.scene=p.scene
                  AND s.stage=p.stage
                LEFT JOIN studio_scene_repair_attempts a
                  ON a.series_id=p.series_id AND a.ordinal=p.ordinal AND
                  a.scene=p.scene AND a.stage=p.stage
                GROUP BY p.series_id,p.ordinal,p.scene,p.stage
                ORDER BY p.series_id,p.ordinal,p.scene,p.stage""").fetchall()
            return {"status":"M31_REPAIR_JOBS_READ_ONLY",
                    "plans":[dict(x) for x in rows],
                    "public_release_authorized":False}
