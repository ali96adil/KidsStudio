"""M26: standing OWNER permission for agent-scheduled PRIVATE-only upload.

The policy authorizes ONLY a bounded YouTube PRIVATE upload to an exact
channel for an approved series. Neither it nor a worker may publish, schedule
public visibility, or grant owner review. One job per exact final render;
a lease may be used only if all current Pi policy/episode/receipt evidence
continues to match. Google OAuth and sensitive media stay on the Mac.
"""
from __future__ import annotations

import json
import sqlite3
import time
from uuid import uuid4

from .series_manager import DIGEST, IDENT
from .studio_queue import StudioQueue, _json_object
from .youtube_private_upload import CHANNEL, JOB, VIDEO


class PrivatePolicyError(ValueError):
    pass


class PrivateUploadPolicy:
    def __init__(self, queue: StudioQueue):
        self.queue=queue

    def initialize(self):
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_youtube_private_policies(
                series_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('ENABLED','PAUSED')),
                max_uploads_24h INTEGER NOT NULL,
                allowed_made_for_kids INTEGER NOT NULL,
                allowed_synthetic_media INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                owner_note TEXT NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(series_id) REFERENCES studio_series(series_id)
            )""")

    def grant(self, series_id: str, *, channel_id: str,
              max_uploads_24h: int, made_for_kids: bool,
              contains_synthetic_media: bool, owner_note: str) -> dict:
        if (not isinstance(series_id,str) or not IDENT.fullmatch(series_id)
            or not isinstance(channel_id,str) or not CHANNEL.fullmatch(channel_id)
            or type(max_uploads_24h) is not int or not 1<=max_uploads_24h<=5
            or type(made_for_kids) is not bool or
            type(contains_synthetic_media) is not bool or
            not isinstance(owner_note,str) or not 15<=len(owner_note.strip())<=500):
            raise PrivatePolicyError("Explicit owner-approved narrow private policy required.")
        with self.queue._connection(write=True) as db:
            series=db.execute("SELECT state FROM studio_series WHERE series_id=?",
                              (series_id,)).fetchone()
            if not series or series["state"] not in ("ACTIVE","PLANNED"):
                raise PrivatePolicyError("Only active or planned approved series.")
            prior=db.execute("""SELECT revision FROM studio_youtube_private_policies
                WHERE series_id=?""",(series_id,)).fetchone()
            revision=prior["revision"]+1 if prior else 1
            db.execute("""INSERT INTO studio_youtube_private_policies VALUES
                (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(series_id) DO UPDATE SET
                channel_id=excluded.channel_id,state=excluded.state,
                max_uploads_24h=excluded.max_uploads_24h,
                allowed_made_for_kids=excluded.allowed_made_for_kids,
                allowed_synthetic_media=excluded.allowed_synthetic_media,
                revision=excluded.revision,owner_note=excluded.owner_note,
                updated_at=excluded.updated_at""",
                (series_id,channel_id,"ENABLED",max_uploads_24h,
                 int(made_for_kids),int(contains_synthetic_media),
                 revision,owner_note.strip(),self.queue.clock()))
        return {"status":"STANDING_PRIVATE_ONLY_PERMISSION_ENABLED",
                "series_id":series_id,"channel_id":channel_id,
                "policy_revision":revision,"public_release_authorized":False}

    def pause(self,series_id: str)->dict:
        with self.queue._connection(write=True) as db:
            changed=db.execute("""UPDATE studio_youtube_private_policies
                SET state='PAUSED',revision=revision+1,updated_at=?
                WHERE series_id=? AND state='ENABLED'""",
                (self.queue.clock(),series_id))
            if changed.rowcount!=1:
                raise PrivatePolicyError("No active private policy to pause.")
            policy=db.execute("SELECT revision FROM studio_youtube_private_policies WHERE series_id=?",
                              (series_id,)).fetchone()
        return {"status":"PRIVATE_UPLOAD_POLICY_PAUSED",
                "policy_revision":policy["revision"],
                "public_release_authorized":False}

    @staticmethod
    def _approved(db: sqlite3.Connection,sid:str,ordinal:int,
                  render_job:str,master_sha:str)->None:
        ep=db.execute("""SELECT e.*,s.state AS series_state FROM studio_episodes e
            JOIN studio_series s ON s.series_id=e.series_id
            WHERE e.series_id=? AND e.ordinal=?""",(sid,ordinal)).fetchone()
        if (not ep or ep["state"]!="EPISODE_APPROVED" or
            ep["series_state"]!="ACTIVE" or
            ep["render_job_id"]!=render_job):
            raise PrivatePolicyError("Current active series approved episode required.")
        job=db.execute("SELECT kind,state,result_json FROM jobs WHERE job_id=?",
                       (render_job,)).fetchone()
        try: receipt=json.loads(job["result_json"] or "{}") if job else {}
        except (ValueError,TypeError):receipt={}
        if (not job or job["kind"] not in ("episode_assemble","godot_render") or
            job["state"]!="COMPLETED" or
            receipt.get("status")!="VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW" or
            receipt.get("artifact_type")!="mp4" or
            receipt.get("artifact_sha256")!=master_sha or
            receipt.get("publication_approved") is not False):
            raise PrivatePolicyError("Pi render SHA does not match current approved master.")
        qa_exists=db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name='studio_quality_reviews'""").fetchone()
        if not qa_exists:
            raise PrivatePolicyError("Final technical QA schema required.")
        qa=db.execute("""SELECT state,checks_passed,media_sha256,review_report_sha256 FROM
            studio_quality_reviews WHERE series_id=? AND ordinal=?
            AND render_job_id=?""",(sid,ordinal,render_job)).fetchone()
        if (not qa or qa["state"] not in (
            "READY_FOR_OWNER_EPISODE_APPROVAL","AI_INTERNAL_READY_PRIVATE_ONLY") or
            qa["checks_passed"]!=11 or qa["media_sha256"]!=master_sha):
            raise PrivatePolicyError("Final technical plus independent reviewer QA incomplete.")
        if qa["state"]=="AI_INTERNAL_READY_PRIVATE_ONLY":
            ai=db.execute("""SELECT status,media_sha256,review_bundle_sha256,
                pedagogy_provider,visual_provider FROM studio_ai_final_reviews
                WHERE series_id=? AND ordinal=? AND render_job_id=?""",
                (sid,ordinal,render_job)).fetchone()
            if (not ai or ai["status"]!="AI_INTERNAL_READY_PRIVATE_ONLY" or
                ai["media_sha256"]!=master_sha or
                ai["review_bundle_sha256"]!=qa["review_report_sha256"] or
                ai["pedagogy_provider"]==ai["visual_provider"]):
                raise PrivatePolicyError("Independent M27 internal reviewer evidence unavailable.")
        if db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
            AND name='studio_private_previews'""").fetchone():
            old=db.execute("""SELECT render_job_id,master_sha256,state
                FROM studio_private_previews WHERE series_id=? AND ordinal=?
                ORDER BY version DESC LIMIT 1""",(sid,ordinal)).fetchone()
            if old and (old["state"]!="REVISION_REQUESTED" or
                        old["render_job_id"]==render_job or
                        old["master_sha256"]==master_sha):
                raise PrivatePolicyError("Already uploaded or same master was rejected.")

    def enqueue_private(self,series_id:str,ordinal:int,*,render_job_id:str,
              master_sha256:str,plan_sha256:str,readiness_sha256:str,
              channel_id:str,made_for_kids:bool,
              contains_synthetic_media:bool)->dict:
        if (not isinstance(series_id,str) or not IDENT.fullmatch(series_id)
            or type(ordinal) is not int or not 1<=ordinal<=120 or
            not isinstance(render_job_id,str) or not JOB.fullmatch(render_job_id)
            or any(not isinstance(x,str) or not DIGEST.fullmatch(x) for x in
                   (master_sha256,plan_sha256,readiness_sha256))
            or not isinstance(channel_id,str) or not CHANNEL.fullmatch(channel_id)
            or type(made_for_kids) is not bool or
            type(contains_synthetic_media) is not bool):
            raise PrivatePolicyError("Exact approved private job/plan/readiness pins required.")
        with self.queue._connection(write=True) as db:
            if db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()[0]:
                raise PrivatePolicyError("Coordinator is paused.")
            policy=db.execute("""SELECT * FROM studio_youtube_private_policies
                WHERE series_id=?""",(series_id,)).fetchone()
            if (not policy or policy["state"]!="ENABLED" or
                policy["channel_id"]!=channel_id or
                bool(policy["allowed_made_for_kids"])!=made_for_kids or
                bool(policy["allowed_synthetic_media"])!=contains_synthetic_media):
                raise PrivatePolicyError("Owner standing PRIVATE-only policy not satisfied.")
            self._approved(db,series_id,ordinal,render_job_id,master_sha256)
            if db.execute("""SELECT 1 FROM jobs WHERE kind='youtube_private_upload'
                AND json_extract(payload,'$.render_job_id')=?""",
                (render_job_id,)).fetchone():
                raise PrivatePolicyError("This exact master already has an upload job.")
            now=self.queue.clock()
            recent=db.execute("""SELECT COUNT(*) FROM jobs WHERE
                kind='youtube_private_upload' AND created_at>=? AND
                json_extract(payload,'$.series_id')=?""",
                (now-86400,series_id)).fetchone()[0]
            if recent>=policy["max_uploads_24h"]:
                raise PrivatePolicyError("Owner 24-hour private upload budget reached.")
            active=db.execute("""SELECT COUNT(*) FROM jobs WHERE
                kind='youtube_private_upload' AND state IN ('QUEUED','LEASED')
                AND json_extract(payload,'$.series_id')=?""",
                (series_id,)).fetchone()[0]
            if active:
                raise PrivatePolicyError("Only one pending PRIVATE upload per series.")
            payload={"series_id":series_id,"episode_number":ordinal,
                     "render_job_id":render_job_id,
                     "master_sha256":master_sha256,"plan_sha256":plan_sha256,
                     "readiness_sha256":readiness_sha256,"channel_id":channel_id,
                     "made_for_kids":made_for_kids,
                     "contains_synthetic_media":contains_synthetic_media,
                     "policy_revision":policy["revision"]}
            job_id=uuid4().hex
            key="private:"+render_job_id
            db.execute("""INSERT INTO jobs(job_id,request_key,kind,payload,state,
                max_attempts,available_at,created_at,updated_at)
                VALUES (?,?,? ,?,'QUEUED',1,?,?,?)""",
                (job_id,key,"youtube_private_upload",
                 _json_object(payload,"private upload"),now,now,now))
            self.queue._event(db,job_id,"ENQUEUED",{
                "kind":"youtube_private_upload","visibility":"PRIVATE"})
        return {"status":"PRIVATE_UPLOAD_QUEUED_NOT_RUN",
                "job_id":job_id,"series_id":series_id,
                "public_release_authorized":False}

    def check_lease(self,job_id:str,generation:int,worker_id:str,
                    payload:dict)->dict:
        if (not isinstance(job_id,str) or not JOB.fullmatch(job_id) or
            type(generation) is not int or generation<1 or
            not isinstance(payload,dict)):
            raise PrivatePolicyError("Valid current Pi lease/proof required.")
        now=self.queue.clock()
        with self.queue._connection() as db:
            db.execute("BEGIN")
            job=self.queue._guard_current(db,job_id,worker_id,generation,now)
            if job["kind"]!="youtube_private_upload" or json.loads(job["payload"])!=payload:
                raise PrivatePolicyError("Upload lease payload differs.")
            if db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()[0]:
                raise PrivatePolicyError("Pi queue paused.")
            policy=db.execute("""SELECT * FROM studio_youtube_private_policies
                WHERE series_id=?""",(payload.get("series_id"),)).fetchone()
            if (not policy or policy["state"]!="ENABLED" or
                policy["channel_id"]!=payload.get("channel_id") or
                policy["revision"]!=payload.get("policy_revision") or
                bool(policy["allowed_made_for_kids"])!=payload.get("made_for_kids") or
                bool(policy["allowed_synthetic_media"])!=payload.get("contains_synthetic_media")):
                raise PrivatePolicyError("Owner policy cancelled or changed.")
            self._approved(db,payload["series_id"],payload["episode_number"],
                           payload["render_job_id"],payload["master_sha256"])
            db.execute("COMMIT")
        return {"status":"CURRENT_PRIVATE_UPLOAD_LEASE_NOT_EXECUTED",
                "job_id":job_id,"generation":generation,
                "plan_sha256":payload["plan_sha256"],
                "master_sha256":payload["master_sha256"],
                "channel_id":payload["channel_id"],
                "visibility":"private",
                "public_release_authorized":False}

    def complete(self,job_id:str,generation:int,worker_id:str,
                 result:dict)->dict:
        expected={"schema_version","status","series_id","episode_number",
                  "render_job_id","video_sha256","video_id","channel_id",
                  "youtube_privacy","processing_status",
                  "platform_privacy_verified","ready_for_owner_review",
                  "public_release_authorized"}
        if (not isinstance(result,dict) or set(result)!=expected or
            type(result.get("schema_version")) is not int or result["schema_version"]!=1 or
            result.get("status") not in (
                "YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING",
                "YOUTUBE_PRIVATE_PROCESSING_PENDING") or
            result.get("public_release_authorized") is not False or
            result.get("youtube_privacy")!="private" or
            result.get("platform_privacy_verified") is not True or
            not isinstance(result.get("video_id"),str) or
            not VIDEO.fullmatch(result["video_id"]) or
            result.get("ready_for_owner_review") is not (
                result.get("status")=="YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING") or
            (result.get("processing_status")=="succeeded") is not (
                result.get("status")=="YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING")):
            raise PrivatePolicyError("Private-only result proof required.")
        with self.queue._connection(write=True) as db:
            leased=self.queue._guard_current(db,job_id,worker_id,generation,
                                            self.queue.clock())
            if leased["kind"]!="youtube_private_upload":
                raise PrivatePolicyError("Upload completion lease mismatch.")
            payload=json.loads(leased["payload"])
            policy=db.execute("""SELECT state,revision FROM studio_youtube_private_policies
                WHERE series_id=?""",(payload["series_id"],)).fetchone()
            if not policy or policy["state"]!="ENABLED" or policy["revision"]!=payload["policy_revision"]:
                raise PrivatePolicyError("Owner revoked upload before completion; manual reconciliation.")
            self._approved(db,payload["series_id"],payload["episode_number"],
                           payload["render_job_id"],payload["master_sha256"])
            if (result.get("series_id")!=payload["series_id"] or
                result.get("episode_number")!=payload["episode_number"] or
                result.get("render_job_id")!=payload["render_job_id"] or
                result.get("video_sha256")!=payload["master_sha256"] or
                result.get("channel_id")!=payload["channel_id"]):
                raise PrivatePolicyError("Reported video differs from authorized upload.")
            # An authenticated, dedicated Mac uploader may hand off a
            # verified PRIVATE video directly to the owner-review queue.
            # This is an authenticated worker assertion, not a Google signature.
            now=self.queue.clock()
            if result["ready_for_owner_review"]:
                installed=db.execute("""SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='studio_private_previews'""").fetchone()
                if not installed:
                    raise PrivatePolicyError("Initialize owner preview ledger before private upload.")
                latest=db.execute("""SELECT state,render_job_id,master_sha256
                    FROM studio_private_previews WHERE series_id=? AND ordinal=?
                    ORDER BY version DESC LIMIT 1""",
                    (payload["series_id"],payload["episode_number"])).fetchone()
                if latest and (latest["state"]!="REVISION_REQUESTED" or
                    latest["render_job_id"]==payload["render_job_id"] or
                    latest["master_sha256"]==payload["master_sha256"]):
                    raise PrivatePolicyError("Existing private review version conflicts.")
                version=db.execute("""SELECT COALESCE(MAX(version),0)+1 FROM
                    studio_private_previews WHERE series_id=? AND ordinal=?""",
                    (payload["series_id"],payload["episode_number"])).fetchone()[0]
                db.execute("""INSERT INTO studio_private_previews(
                    video_id,series_id,ordinal,render_job_id,master_sha256,
                    state,version,claimed_visibility,platform_privacy_verified,
                    recorded_at) VALUES (?,?,?,?,?,'PRIVATE_AWAITING_OWNER_REVIEW',
                    ?,'PRIVATE',1,?)""",
                    (result["video_id"],payload["series_id"],payload["episode_number"],
                     payload["render_job_id"],payload["master_sha256"],version,now))
            db.execute("""UPDATE jobs SET state='COMPLETED',worker_id=NULL,
                lease_expires=NULL,updated_at=?,result_json=?
                WHERE job_id=?""",(now,_json_object(result,"private upload result"),job_id))
            self.queue._event(db,job_id,"COMPLETED",{
                "status":"PRIVATE_VERIFIED" if result.get("ready_for_owner_review")
                else "PRIVATE_PROCESSING_PENDING"})
        return {"status":"PRIVATE_UPLOAD_RECEIPT_RECORDED_NOT_PUBLIC",
                "job_id":job_id,
                "owner_review_queued":result["ready_for_owner_review"],
                "public_release_authorized":False}
