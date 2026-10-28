"""M13 opt-in scene-level owner approvals for multi-scene episodes.

Additive Studio Brain schema. Every scene has an immutable owner-registered
script SHA and independently leased voice→LTX jobs. Does not run models,
transfer private scene scripts, approve generated media or publish anything.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
from uuid import uuid4

from .studio_queue import StudioQueue, _json_object
from .episode_assembly import digest, _ensure_private

SHA=re.compile(r"^[a-f0-9]{64}$")
ID=re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
RECIPE=re.compile(r"^[A-Za-z0-9_-]{1,80}$")
STAGES={
    "voice_synthesize":("VOICE_RENDERED_PENDING_QA","wav"),
    "ltx_animate":("A2V_RENDERED_PENDING_QA","mp4")
}


class SceneError(ValueError):
    """Scene provenance or required owner QA missing."""


class SceneLedger:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_scene_plans(
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                plan_sha256 TEXT NOT NULL, episode_script_sha256 TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal),
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_episodes(series_id,ordinal)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_scenes(
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                scene INTEGER NOT NULL, script_sha256 TEXT NOT NULL,
                objective TEXT NOT NULL,
                PRIMARY KEY(series_id,ordinal,scene),
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_scene_plans(series_id,ordinal)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_scene_stages(
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                scene INTEGER NOT NULL, stage TEXT NOT NULL,
                state TEXT NOT NULL, job_id TEXT NOT NULL,
                scene_script_sha256 TEXT NOT NULL,
                source_voice_sha256 TEXT,
                artifact_sha256 TEXT,
                owner_note TEXT,
                updated_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,scene,stage),
                FOREIGN KEY(series_id,ordinal,scene)
                REFERENCES studio_scenes(series_id,ordinal,scene)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_scene_audio_checks(
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                scene INTEGER NOT NULL, ltx_job_id TEXT NOT NULL,
                report_sha256 TEXT NOT NULL,
                voice_sha256 TEXT NOT NULL, a2v_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY(series_id,ordinal,scene,ltx_job_id),
                FOREIGN KEY(series_id,ordinal,scene)
                REFERENCES studio_scenes(series_id,ordinal,scene)
            )""")

            db.execute("""CREATE TABLE IF NOT EXISTS studio_scene_voice_checks(
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                scene INTEGER NOT NULL, voice_job_id TEXT NOT NULL,
                voice_sha256 TEXT NOT NULL, report_sha256 TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,scene,voice_job_id),
                FOREIGN KEY(series_id,ordinal,scene)
                REFERENCES studio_scenes(series_id,ordinal,scene)
            )""")

    def register_plan(self, filename: str|Path) -> dict:
        path=Path(filename).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise SceneError("Scene plan must be absolute and owner-local, not symlinked.")
        path=path.resolve()
        _ensure_private(path.parent)
        if not path.is_file() or not 0<path.stat().st_size<=100000:
            raise SceneError("Private scene plan missing or oversized.")
        try:
            manifest=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise SceneError("Invalid scene-plan JSON.") from exc
        if not isinstance(manifest,dict) or set(manifest)!={
                "schema_version","series_id","episode_number",
                "episode_script_sha256","scenes"}:
            raise SceneError("Unknown/missing owner scene plan fields.")
        sid=manifest["series_id"]
        ordinal=manifest["episode_number"]
        sha=manifest["episode_script_sha256"]
        if (manifest["schema_version"]!=1 or not isinstance(sid,str) or
            not ID.fullmatch(sid) or type(ordinal) is not int or
            not 1<=ordinal<=120 or not isinstance(sha,str) or not SHA.fullmatch(sha)):
            raise SceneError("Invalid episode identity/hash.")
        scenes=manifest["scenes"]
        if not isinstance(scenes,list) or not 2<=len(scenes)<=40:
            raise SceneError("Require 2–40 separately pinned scenes.")
        seen=set()
        for index,item in enumerate(scenes,1):
            if not isinstance(item,dict) or set(item)!={"scene","script_sha256","objective"}:
                raise SceneError("Each scene requires order, script SHA and objective.")
            if (type(item["scene"]) is not int or item["scene"]!=index or
                not isinstance(item["script_sha256"],str) or
                not SHA.fullmatch(item["script_sha256"]) or
                not isinstance(item["objective"],str) or
                not 5<=len(item["objective"].strip())<=220):
                raise SceneError("Scene order and objective must be complete.")
            if item["script_sha256"] in seen:
                raise SceneError("Duplicate scene script hash; check real scene split.")
            seen.add(item["script_sha256"])
        with self.queue._connection(write=True) as db:
            ep=db.execute("""SELECT e.state,e.source_sha256,
                s.state AS series_state FROM studio_episodes e
                JOIN studio_series s USING(series_id)
                WHERE e.series_id=? AND e.ordinal=?""",(sid,ordinal)).fetchone()
            if (ep is None or ep["state"]!="SCRIPT_APPROVED" or
                ep["series_state"]!="ACTIVE" or ep["source_sha256"]!=sha):
                raise SceneError("Approved parent script in active series required.")
            if db.execute("""SELECT 1 FROM studio_scene_plans
                WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone():
                raise SceneError("Immutable scene plan already registered.")
            stamp=time.time()
            plan_sha=digest(path)
            db.execute("""INSERT INTO studio_scene_plans VALUES (?,?,?,?,?)""",
                       (sid,ordinal,plan_sha,sha,stamp))
            for item in scenes:
                db.execute("""INSERT INTO studio_scenes VALUES (?,?,?,?,?)""",
                           (sid,ordinal,item["scene"],item["script_sha256"],
                            item["objective"].strip()))
        return {"status":"SCENE_PLAN_PINNED_NOT_RENDERED","series_id":sid,
                "episode_number":ordinal,"scene_count":len(scenes),
                "plan_sha256":plan_sha,"publication_approved":False}

    def queue_stage(self, sid:str,ordinal:int,scene:int,kind:str,recipe:str)->str:
        if (kind not in STAGES or not isinstance(recipe,str) or
            not RECIPE.fullmatch(recipe) or type(scene) is not int or scene<1):
            raise SceneError("Approved scene, media capability and recipe ID required.")
        with self.queue._connection(write=True) as db:
            paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
            if not paused or paused["paused"]:
                raise SceneError("Studio queue paused; no new scene media tasks.")
            ep=db.execute("""SELECT e.state,e.source_sha256,
                    s.state AS series_state FROM studio_episodes e
                    JOIN studio_series s USING(series_id)
                    WHERE e.series_id=? AND e.ordinal=?""",(sid,ordinal)).fetchone()
            plan=db.execute("""SELECT episode_script_sha256 FROM studio_scene_plans
                    WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone()
            item=db.execute("""SELECT script_sha256 FROM studio_scenes
                    WHERE series_id=? AND ordinal=? AND scene=?""",
                    (sid,ordinal,scene)).fetchone()
            if (not ep or ep["state"]!="SCRIPT_APPROVED" or
                ep["series_state"]!="ACTIVE" or not plan or
                plan["episode_script_sha256"]!=ep["source_sha256"] or not item):
                raise SceneError("Current active, approved multi-scene plan required.")
            if db.execute("""SELECT 1 FROM studio_scene_stages WHERE
                  series_id=? AND ordinal=? AND scene=? AND stage=?""",
                  (sid,ordinal,scene,kind)).fetchone():
                raise SceneError("Scene stage already queued; never auto-repeat.")
            payload={"recipe_id":recipe,"script_sha256":item["script_sha256"]}
            if kind=="ltx_animate":
                voice=db.execute("""SELECT state,artifact_sha256,scene_script_sha256
                    FROM studio_scene_stages WHERE
                    series_id=? AND ordinal=? AND scene=?
                    AND stage='voice_synthesize'""",(sid,ordinal,scene)).fetchone()
                if (not voice or voice["state"]!="QA_APPROVED" or
                    voice["scene_script_sha256"]!=item["script_sha256"] or
                    not isinstance(voice["artifact_sha256"],str) or
                    not SHA.fullmatch(voice["artifact_sha256"])):
                    raise SceneError("Owner-approved scene WAV required before LTX.")
                payload["voice_sha256"]=voice["artifact_sha256"]
            packed=_json_object(payload,"payload")
            job_id=uuid4().hex
            now=self.queue.clock()
            key=f"scene:{sid}:episode:{ordinal}:s{scene}:{kind}:{item['script_sha256'][:16]}"
            db.execute("""INSERT INTO jobs
                (job_id,request_key,kind,payload,state,max_attempts,
                available_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (job_id,key,kind,packed,"QUEUED",1,now,now,now))
            self.queue._event(db,job_id,"ENQUEUED",{"kind":kind})
            db.execute("""INSERT INTO studio_scene_stages(
                series_id,ordinal,scene,stage,state,job_id,
                scene_script_sha256,source_voice_sha256,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (sid,ordinal,scene,kind,"QUEUED",job_id,
                 item["script_sha256"],payload.get("voice_sha256"),time.time()))
            return job_id

    def queue_first_voice_pilot(self, sid:str, ordinal:int, recipe:str,
                                plan_sha256:str, owner_note:str)->str:
        """M22: deliberate ONE-SCENE pilot queue; never an execution permit.

        The owner must separately run M21. In a single IMMEDIATE SQLite
        transaction recheck current approval, series, plan, source, audit
        and zero existing stages before enqueueing exactly scene 1.
        """
        if (not isinstance(sid,str) or not ID.fullmatch(sid) or
            type(ordinal) is not int or not 1<=ordinal<=120 or
            not isinstance(recipe,str) or not RECIPE.fullmatch(recipe) or
            not isinstance(plan_sha256,str) or not SHA.fullmatch(plan_sha256) or
            not isinstance(owner_note,str) or
            not 12<=len(owner_note.strip())<=500):
            raise SceneError("Pilot requires owner note, recipe and exact frozen plan SHA.")
        with self.queue._connection(write=True) as db:
            if db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()[0]:
                raise SceneError("Coordinator paused; do not enqueue pilot.")
            row=db.execute("""SELECT e.state,e.source_sha256,e.owner_review_note,
                s.state AS series_state,p.plan_sha256,p.episode_script_sha256
                FROM studio_episodes e JOIN studio_series s USING(series_id)
                JOIN studio_scene_plans p ON p.series_id=e.series_id AND
                p.ordinal=e.ordinal
                WHERE e.series_id=? AND e.ordinal=?""",(sid,ordinal)).fetchone()
            scene=db.execute("""SELECT scene,script_sha256 FROM studio_scenes
                WHERE series_id=? AND ordinal=? ORDER BY scene""",
                (sid,ordinal)).fetchall()
            owner_script=db.execute("""SELECT 1 FROM studio_series_audit
                WHERE series_id=? AND ordinal=? AND
                action='SCRIPT_APPROVED_BY_OWNER'""",
                (sid,ordinal)).fetchone()
            ai_script=None
            if db.execute("""SELECT 1 FROM sqlite_master WHERE
                type='table' AND name='studio_script_ai_reviews'""").fetchone():
                ai_script=db.execute("""SELECT 1 FROM studio_script_ai_reviews r
                    JOIN studio_episodes e ON e.series_id=r.series_id
                      AND e.ordinal=r.ordinal AND e.revision=r.revision
                    WHERE r.series_id=? AND r.ordinal=? AND
                      r.verdict='AI_SCRIPT_PRIVATE_READY' AND
                      r.original_sha256=e.source_sha256 AND
                      r.first_provider!=r.second_provider""",
                    (sid,ordinal)).fetchone()
            if (not row or row["state"]!="SCRIPT_APPROVED" or
                row["series_state"]!="ACTIVE" or
                row["plan_sha256"]!=plan_sha256 or
                row["episode_script_sha256"]!=row["source_sha256"] or
                not isinstance(row["owner_review_note"],str) or
                len(row["owner_review_note"].strip())<5 or
                len(scene)!=2 or scene[0]["scene"]!=1 or
                scene[1]["scene"]!=2 or
                not (owner_script or ai_script)):
                raise SceneError("Owner-approved two-scene M13 plan required.")
            if db.execute("""SELECT 1 FROM studio_scene_stages WHERE
                series_id=? AND ordinal=? LIMIT 1""",
                (sid,ordinal)).fetchone():
                raise SceneError("Pilot voice stage already initiated; reconcile manually.")
            payload=_json_object({
                "recipe_id":recipe,
                "script_sha256":scene[0]["script_sha256"],
                "pilot_scene":1,
                "pilot_plan_sha256":plan_sha256,
            },"payload")
            job_id=uuid4().hex
            now=self.queue.clock()
            key=f"scene:{sid}:episode:{ordinal}:s1:voice_synthesize:{scene[0]['script_sha256'][:16]}"
            db.execute("""INSERT INTO jobs
                (job_id,request_key,kind,payload,state,max_attempts,
                available_at,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (job_id,key,"voice_synthesize",payload,"QUEUED",1,now,now,now))
            self.queue._event(db,job_id,"ENQUEUED",{"kind":"voice_synthesize"})
            db.execute("""INSERT INTO studio_scene_stages(
                series_id,ordinal,scene,stage,state,job_id,
                scene_script_sha256,source_voice_sha256,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (sid,ordinal,1,"voice_synthesize","QUEUED",job_id,
                 scene[0]["script_sha256"],None,time.time()))
            db.execute("""INSERT INTO studio_series_notes
                (series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
                (sid,ordinal,"FIRST_VOICE_PILOT: "+owner_note.strip(),time.time()))
            return job_id

    def queue_first_voice_ai(self,sid:str,ordinal:int,recipe:str,
                             plan_sha256:str)->str:
        """M30: single internally AI-approved two-scene pilot; no owner signoff.

        The transaction inside queue_first_voice_pilot is still the final
        admission gate, and must see a current 2-provider M30 review.
        This method never executes models or declares PUBLIC approval.
        """
        with self.queue._connection() as db:
            exists=db.execute("""SELECT 1 FROM sqlite_master WHERE
                type='table' AND name='studio_script_ai_reviews'""").fetchone()
            if not exists:
                raise SceneError("M30 signed internal script review schema missing.")
            ai=db.execute("""SELECT 1 FROM studio_script_ai_reviews r
                JOIN studio_episodes e ON e.series_id=r.series_id
                    AND e.ordinal=r.ordinal AND e.revision=r.revision
                WHERE r.series_id=? AND r.ordinal=? AND
                  r.verdict='AI_SCRIPT_PRIVATE_READY' AND
                  r.original_sha256=e.source_sha256 AND
                  r.first_provider!=r.second_provider AND
                  e.state='SCRIPT_APPROVED'""",(sid,ordinal)).fetchone()
            if not ai:
                raise SceneError("Current independently reviewed AI script required.")
        return self.queue_first_voice_pilot(
            sid,ordinal,recipe,plan_sha256,
            "M30_AI_TWO_MODEL_PRIVATE_ONLY_OWNER_POST_VIDEO_REVIEW")

    def reconcile(self)->int:
        count=0
        with self.queue._connection(write=True) as db:
            rows=db.execute("""SELECT * FROM studio_scene_stages WHERE
                state='QUEUED'""").fetchall()
            for row in rows:
                job=db.execute("SELECT * FROM jobs WHERE job_id=?",
                               (row["job_id"],)).fetchone()
                if not job or job["kind"]!=row["stage"]:
                    raise SceneError("Scene job reference missing or wrong type.")
                if job["state"] in ("FAILED","CANCELLED"):
                    state="BLOCKED";sha=None
                elif job["state"]=="COMPLETED":
                    try: receipt=json.loads(job["result_json"] or "{}")
                    except (TypeError,ValueError): receipt={}
                    required_status,typ=STAGES[row["stage"]]
                    valid=(receipt.get("status")==required_status and
                           receipt.get("artifact_type")==typ and
                           receipt.get("publication_approved") is False and
                           isinstance(receipt.get("artifact_sha256"),str) and
                           SHA.fullmatch(receipt["artifact_sha256"]))
                    state="PENDING_QA" if valid else "BLOCKED"
                    sha=receipt["artifact_sha256"] if valid else None
                else:
                    continue
                db.execute("""UPDATE studio_scene_stages SET state=?,
                    artifact_sha256=?,updated_at=? WHERE
                    series_id=? AND ordinal=? AND scene=? AND stage=?""",
                    (state,sha,time.time(),row["series_id"],row["ordinal"],
                     row["scene"],row["stage"]))
                count+=1
        return count

    def register_voice_technical(self,sid:str,ordinal:int,scene:int,
                                 report_file:str|Path)->dict:
        """M23: link exact offline WAV technical report to current Pi pilot.

        This receipt itself does not attest true sound or substitute for the
        owner listening. It cannot approve voice or start LTX.
        """
        from .voice_qa import CHECKS as WAV_CHECKS
        path=Path(report_file).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise SceneError("Voice QA report must be an absolute private file.")
        path=path.resolve()
        _ensure_private(path.parent)
        if (not path.is_file() or path.suffix!=".json" or
            not 0<path.stat().st_size<=40_000):
            raise SceneError("Missing or oversized private voice report.")
        try: r=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise SceneError("Invalid voice QA JSON.") from exc
        fields={"schema_version","status","job_id","script_sha256",
                "voice_sha256","expected_voice_sha256","voice_bytes",
                "duration_seconds","sample_rate_hz","channels",
                "rms_dbfs","clipped_fraction","quiet_fraction","checks",
                "owner_listening_performed","text_matches_audio_verified",
                "speaker_identity_verified","commercial_rights_verified",
                "publishing_approved"}
        if (not isinstance(r,dict) or set(r)!=fields or
            type(r["schema_version"]) is not int or r["schema_version"]!=1 or
            r["status"]!="VOICE_TECH_PASS_OWNER_LISTENING_PENDING" or
            not isinstance(r["checks"],dict) or
            set(r["checks"])!=set(WAV_CHECKS) or
            any(r["checks"][name] is not True for name in WAV_CHECKS) or
            r["owner_listening_performed"] is not False or
            r["text_matches_audio_verified"] is not False or
            r["speaker_identity_verified"] is not False or
            r["commercial_rights_verified"] is not False or
            r["publishing_approved"] is not False or
            type(r["voice_bytes"]) is not int or r["voice_bytes"]<100 or
            type(r["duration_seconds"]) not in (int,float) or
            not 0.2<=r["duration_seconds"]<=180 or
            type(r["rms_dbfs"]) not in (int,float) or
            not -48<=r["rms_dbfs"]<=-3 or
            type(r["clipped_fraction"]) not in (int,float) or
            not 0<=r["clipped_fraction"]<=0.01 or
            type(r["quiet_fraction"]) not in (int,float) or
            not 0<=r["quiet_fraction"]<=0.90 or
            type(r["sample_rate_hz"]) is not int or
            not 16000<=r["sample_rate_hz"]<=96000 or
            type(r["channels"]) is not int or r["channels"] not in (1,2)):
            raise SceneError("WAV technical checks must all pass and remain unapproved.")
        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT st.job_id,st.state,st.artifact_sha256,
                st.scene_script_sha256,j.kind,j.state AS job_state,
                j.payload,j.result_json FROM studio_scene_stages st
                JOIN jobs j ON st.job_id=j.job_id
                WHERE st.series_id=? AND st.ordinal=? AND st.scene=?
                AND st.stage='voice_synthesize'""",(sid,ordinal,scene)).fetchone()
            if not row or row["state"]!="PENDING_QA" or row["job_state"]!="COMPLETED" or row["kind"]!="voice_synthesize":
                raise SceneError("Current completed pilot voice receipt required.")
            try:
                payload=json.loads(row["payload"])
                receipt=json.loads(row["result_json"] or "{}")
            except (ValueError,TypeError) as exc:
                raise SceneError("Malformed current voice receipt.") from exc
            pilot=payload.get("pilot_scene")
            if ((pilot is not None and (type(pilot) is not int or
                 pilot!=scene or scene!=1)) or
                (pilot is None and "pilot_plan_sha256" in payload) or
                payload.get("script_sha256")!=row["scene_script_sha256"] or
                r["script_sha256"]!=row["scene_script_sha256"] or
                r["job_id"]!=row["job_id"] or
                r["voice_sha256"]!=row["artifact_sha256"] or
                r["expected_voice_sha256"]!=row["artifact_sha256"] or
                receipt.get("artifact_sha256")!=r["voice_sha256"] or
                receipt.get("artifact_bytes")!=r["voice_bytes"] or
                receipt.get("status")!="VOICE_RENDERED_PENDING_QA" or
                receipt.get("artifact_type")!="wav" or
                receipt.get("publication_approved") is not False):
                raise SceneError("Voice technical report and owner-pinned Pi job disagree.")
            if db.execute("""SELECT 1 FROM studio_scene_voice_checks
                WHERE series_id=? AND ordinal=? AND scene=? AND
                voice_job_id=?""",(sid,ordinal,scene,row["job_id"])).fetchone():
                raise SceneError("Voice QA already registered; never overwrite.")
            db.execute("""INSERT INTO studio_scene_voice_checks VALUES (?,?,?,?,?,?,?,?)""",
                (sid,ordinal,scene,row["job_id"],r["voice_sha256"],
                 digest(path),"TECH_PASS_OWNER_LISTENING_PENDING",time.time()))
        return {"status":"VOICE_TECH_REGISTERED_AWAITING_OWNER_LISTENING",
                "scene":scene,"voice_sha256":r["voice_sha256"],
                "owner_listening_performed":False,"publication_approved":False}

    def register_audio(self,sid:str,ordinal:int,scene:int,report_file:str|Path)->None:
        path=Path(report_file).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise SceneError("Private audio continuity report must be absolute.")
        path=path.resolve()
        _ensure_private(path.parent)
        if not path.is_file() or not 0<path.stat().st_size<=40000:
            raise SceneError("Audio report missing or oversized.")
        try:r=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:raise SceneError("Invalid audio report.") from exc
        fields={"schema_version","status","voice_sha256","a2v_sha256",
                "voice_seconds","a2v_audio_seconds","duration_close",
                "envelope_correlation","estimated_lag_seconds","energy_present",
                "audio_content_identity_proven","speaker_identity_proven",
                "lip_sync_verified","owner_audiovisual_review_required",
                "publishing_approved"}
        if (not isinstance(r,dict) or set(r)!=fields or r["schema_version"]!=1
            or r["status"]!="AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED"
            or r["duration_close"] is not True or r["energy_present"] is not True
            or type(r["envelope_correlation"]) not in (int,float)
            or not .82<=r["envelope_correlation"]<=1
            or type(r["estimated_lag_seconds"]) not in (int,float)
            or abs(r["estimated_lag_seconds"])>.6
            or r["audio_content_identity_proven"] is not False
            or r["speaker_identity_proven"] is not False
            or r["lip_sync_verified"] is not False
            or r["owner_audiovisual_review_required"] is not True
            or r["publishing_approved"] is not False):
            raise SceneError("Source audio compatibility evidence failed.")
        with self.queue._connection(write=True) as db:
            rows=db.execute("""SELECT stage,state,job_id,artifact_sha256,
                    source_voice_sha256 FROM studio_scene_stages
                    WHERE series_id=? AND ordinal=? AND scene=?""",
                    (sid,ordinal,scene)).fetchall()
            by_kind={item["stage"]:item for item in rows}
            voice=by_kind.get("voice_synthesize")
            ltx=by_kind.get("ltx_animate")
            if (not voice or voice["state"]!="QA_APPROVED" or
                not ltx or ltx["state"]!="PENDING_QA" or
                r["voice_sha256"]!=voice["artifact_sha256"] or
                r["a2v_sha256"]!=ltx["artifact_sha256"] or
                ltx["source_voice_sha256"]!=voice["artifact_sha256"]):
                raise SceneError("Audio evidence disagrees with current scene output.")
            db.execute("""INSERT INTO studio_scene_audio_checks VALUES (?,?,?,?,?,?,?,?)""",
                (sid,ordinal,scene,ltx["job_id"],digest(path),
                 r["voice_sha256"],r["a2v_sha256"],
                 "TECH_COMPATIBLE_HUMAN_QA_REQUIRED"))

    def approve(self,sid:str,ordinal:int,scene:int,kind:str,
                artifact_sha256:str,note:str, *,
                owner_listened:bool=False)->None:
        if (kind not in STAGES or not isinstance(artifact_sha256,str) or
            not SHA.fullmatch(artifact_sha256) or not isinstance(note,str) or
            not 12<=len(note.strip())<=500):
            raise SceneError("Owner note and exact media SHA256 required.")
        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT * FROM studio_scene_stages WHERE
                series_id=? AND ordinal=? AND scene=? AND stage=?""",
                (sid,ordinal,scene,kind)).fetchone()
            if (not row or row["state"]!="PENDING_QA"
                or row["artifact_sha256"]!=artifact_sha256):
                raise SceneError("Current scene media receipt requires owner QA.")
            if kind=="voice_synthesize":
                job=db.execute("SELECT kind,payload FROM jobs WHERE job_id=?",
                               (row["job_id"],)).fetchone()
                if job and job["kind"]=="voice_synthesize":
                    try: payload=json.loads(job["payload"])
                    except (ValueError,TypeError):payload={}
                    if "pilot_scene" in payload:
                        evidence=db.execute("""SELECT 1
                            FROM studio_scene_voice_checks WHERE
                            series_id=? AND ordinal=? AND scene=? AND
                            voice_job_id=? AND voice_sha256=? AND
                            status='TECH_PASS_OWNER_LISTENING_PENDING'""",
                            (sid,ordinal,scene,row["job_id"],
                             artifact_sha256)).fetchone()
                        if not evidence or owner_listened is not True:
                            raise SceneError("M23 exact voice QA and explicit owner listening required.")
            if kind=="ltx_animate":
                evidence=db.execute("""SELECT 1 FROM studio_scene_audio_checks WHERE
                    series_id=? AND ordinal=? AND scene=? AND ltx_job_id=?
                    AND a2v_sha256=? AND status='TECH_COMPATIBLE_HUMAN_QA_REQUIRED'""",
                    (sid,ordinal,scene,row["job_id"],artifact_sha256)).fetchone()
                if not evidence:
                    raise SceneError("M10 scene audio evidence required before LTX QA.")
            db.execute("""UPDATE studio_scene_stages SET state='QA_APPROVED',
                owner_note=?,updated_at=? WHERE series_id=? AND ordinal=? AND
                scene=? AND stage=?""",
                (note.strip(),time.time(),sid,ordinal,scene,kind))

    def snapshot(self,sid:str,ordinal:int)->dict:
        with self.queue._connection() as db:
            plan=db.execute("""SELECT plan_sha256 FROM studio_scene_plans
                WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone()
            if not plan:
                raise SceneError("No pinned owner multi-scene plan.")
            rows=db.execute("""SELECT s.scene,s.script_sha256,s.objective,
                t.stage,t.state,t.job_id,t.artifact_sha256,t.source_voice_sha256
                FROM studio_scenes s LEFT JOIN studio_scene_stages t USING
                (series_id,ordinal,scene)
                WHERE s.series_id=? AND s.ordinal=?
                ORDER BY s.scene,t.stage""",(sid,ordinal)).fetchall()
        scenes={}
        for row in rows:
            scene=scenes.setdefault(row["scene"],{
                "scene":row["scene"],"script_sha256":row["script_sha256"],
                "objective":row["objective"],"stages":{}})
            if row["stage"]:
                scene["stages"][row["stage"]]={
                    "state":row["state"],"job_id":row["job_id"],
                    "artifact_sha256":row["artifact_sha256"],
                    "source_voice_sha256":row["source_voice_sha256"]}
        return {"series_id":sid,"episode_number":ordinal,
                "plan_sha256":plan["plan_sha256"],
                "scene_count":len(scenes),
                "scenes":list(scenes.values()),
                "publication_approved":False}


def assert_scenes_ready(db, sid: str, ordinal: int,
                        episode_script_sha: str) -> list[dict]:
    """Return exact ordered approved scene receipts or fail closed.

    Caller owns an existing Studio Brain transaction; no writes performed.
    """
    plan=db.execute("""SELECT episode_script_sha256 FROM studio_scene_plans
        WHERE series_id=? AND ordinal=?""",(sid,ordinal)).fetchone()
    if not plan or plan["episode_script_sha256"]!=episode_script_sha:
        raise SceneError("Owner-approved scene plan differs from parent script.")
    scenes=db.execute("""SELECT scene,script_sha256 FROM studio_scenes
        WHERE series_id=? AND ordinal=? ORDER BY scene""",
        (sid,ordinal)).fetchall()
    if not 2<=len(scenes)<=40 or [x["scene"] for x in scenes]!=list(range(1,len(scenes)+1)):
        raise SceneError("Contiguous 2–40 scene plan required.")
    ready=[]
    for scene in scenes:
        index=scene["scene"]
        parts=db.execute("""SELECT * FROM studio_scene_stages WHERE
            series_id=? AND ordinal=? AND scene=?""",
            (sid,ordinal,index)).fetchall()
        by_kind={row["stage"]:row for row in parts}
        if len(parts)!=2 or set(by_kind)!=set(STAGES):
            raise SceneError("Every scene requires voice and LTX stages.")
        voice=by_kind["voice_synthesize"]
        ltx=by_kind["ltx_animate"]
        if (voice["state"]!="QA_APPROVED" or ltx["state"]!="QA_APPROVED" or
            voice["scene_script_sha256"]!=scene["script_sha256"] or
            ltx["scene_script_sha256"]!=scene["script_sha256"] or
            ltx["source_voice_sha256"]!=voice["artifact_sha256"]):
            raise SceneError("Scene lacks approved WAV or matched LTX.")
        evidence=db.execute("""SELECT 1 FROM studio_scene_audio_checks
            WHERE series_id=? AND ordinal=? AND scene=?
            AND ltx_job_id=? AND voice_sha256=? AND a2v_sha256=?
            AND status='TECH_COMPATIBLE_HUMAN_QA_REQUIRED'""",
            (sid,ordinal,index,ltx["job_id"],
             voice["artifact_sha256"],ltx["artifact_sha256"])).fetchone()
        if not evidence:
            raise SceneError("Current scene audio technical evidence missing.")
        for kind,row,status,typ in (
            ("voice_synthesize",voice,"VOICE_RENDERED_PENDING_QA","wav"),
            ("ltx_animate",ltx,"A2V_RENDERED_PENDING_QA","mp4")
        ):
            job=db.execute("""SELECT kind,state,result_json FROM jobs
                WHERE job_id=?""",(row["job_id"],)).fetchone()
            try: result=json.loads(job["result_json"] or "{}") if job else {}
            except (TypeError,ValueError):result={}
            if (not job or job["kind"]!=kind or job["state"]!="COMPLETED"
                or result.get("status")!=status or result.get("artifact_type")!=typ
                or result.get("artifact_sha256")!=row["artifact_sha256"]
                or result.get("publication_approved") is not False):
                raise SceneError("Scene owner QA not backed by completed Pi receipt.")
        ready.append({
            "scene":index,
            "script_sha256":scene["script_sha256"],
            "voice_job_id":voice["job_id"],
            "voice_sha256":voice["artifact_sha256"],
            "ltx_job_id":ltx["job_id"],
            "ltx_sha256":ltx["artifact_sha256"],
        })
    return ready
