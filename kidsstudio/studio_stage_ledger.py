"""Owner-gated voice -> LTX production task ledger in Studio Brain SQLite.

Only creates typed Pi media jobs and reconciles authenticated queue receipts.
No model calls, file reads from Mac, privileges, or automated public approval.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from uuid import uuid4

from .studio_queue import StudioQueue, _json_object

SAFE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
STAGES = {"voice_synthesize": ("VOICE_RENDERED_PENDING_QA", "wav"),
          "ltx_animate": ("A2V_RENDERED_PENDING_QA", "mp4")}


class StageLedgerError(ValueError):
    """Unknown stage, inconsistent provenance or unauthorised transition."""


class StageLedger:
    def __init__(self, queue: StudioQueue):
        self.queue=queue

    def initialize(self) -> None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_episode_stages (
                series_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                stage TEXT NOT NULL,
                state TEXT NOT NULL,
                job_id TEXT,
                script_sha256 TEXT NOT NULL,
                source_voice_sha256 TEXT,
                artifact_sha256 TEXT,
                owner_note TEXT,
                attempt INTEGER NOT NULL DEFAULT 1,
                updated_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,stage),
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_episodes(series_id,ordinal)
            )""")

    def queue_stage(self, series_id: str, ordinal: int,
                    stage: str, recipe_id: str) -> str:
        if stage not in STAGES:
            raise StageLedgerError("Unsupported independent media stage.")
        if type(ordinal) is not int or ordinal <= 0:
            raise StageLedgerError("Invalid episode.")
        if not isinstance(recipe_id,str) or not SAFE.fullmatch(recipe_id):
            raise StageLedgerError("Approved local stage recipe ID required.")
        with self.queue._connection(write=True) as db:
            ep=db.execute("""SELECT e.*,s.state AS series_state
                FROM studio_episodes e JOIN studio_series s USING(series_id)
                WHERE e.series_id=? AND e.ordinal=?""",
                (series_id,ordinal)).fetchone()
            if ep is None or ep["series_state"]!="ACTIVE" or ep["state"]!="SCRIPT_APPROVED":
                raise StageLedgerError("Owner-approved script in active series required.")
            script=ep["source_sha256"]
            if not isinstance(script,str) or not SHA.fullmatch(script):
                raise StageLedgerError("Approved source hash missing.")
            row=db.execute("""SELECT * FROM studio_episode_stages
                WHERE series_id=? AND ordinal=? AND stage=?""",
                (series_id,ordinal,stage)).fetchone()
            if row and row["state"]!="RESET_FOR_RETRY":
                raise StageLedgerError("Stage already exists; never silently overwrite.")
            attempt=row["attempt"] if row else 1
            payload={"recipe_id":recipe_id,"script_sha256":script}
            prior_voice=None
            if stage=="ltx_animate":
                prior_voice=db.execute("""SELECT * FROM studio_episode_stages
                   WHERE series_id=? AND ordinal=? AND stage='voice_synthesize'""",
                   (series_id,ordinal)).fetchone()
                if (prior_voice is None or prior_voice["state"]!="QA_APPROVED" or
                    prior_voice["script_sha256"]!=script or
                    not isinstance(prior_voice["artifact_sha256"],str) or
                    not SHA.fullmatch(prior_voice["artifact_sha256"])):
                    raise StageLedgerError("Owner-verified voice receipt required before LTX.")
                payload["voice_sha256"]=prior_voice["artifact_sha256"]
            key=f"series:{series_id}:episode:{ordinal}:{stage}:a{attempt}:{script[:16]}"
            packed=_json_object(payload,"payload")
            prior=db.execute("SELECT * FROM jobs WHERE request_key=?",(key,)).fetchone()
            if prior is not None:
                if prior["kind"]!=stage or prior["payload"]!=packed:
                    raise StageLedgerError("Conflicting idempotent stage request.")
                job_id=prior["job_id"]
            else:
                now=self.queue.clock()
                job_id=uuid4().hex
                db.execute("""INSERT INTO jobs
                    (job_id,request_key,kind,payload,state,max_attempts,
                     available_at,created_at,updated_at)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                    (job_id,key,stage,packed,"QUEUED",1,now,now,now))
                self.queue._event(db,job_id,"ENQUEUED",{"kind":stage})
            db.execute("""INSERT INTO studio_episode_stages
                    (series_id,ordinal,stage,state,job_id,script_sha256,
                     source_voice_sha256,attempt,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(series_id,ordinal,stage) DO UPDATE SET
                     state=excluded.state,job_id=excluded.job_id,
                     script_sha256=excluded.script_sha256,
                     source_voice_sha256=excluded.source_voice_sha256,
                     artifact_sha256=NULL,owner_note=NULL,updated_at=excluded.updated_at""",
                (series_id,ordinal,stage,"QUEUED",job_id,script,
                 payload.get("voice_sha256"),attempt,time.time()))
            return job_id

    def reconcile(self) -> int:
        changed=0
        with self.queue._connection(write=True) as db:
            rows=db.execute("""SELECT * FROM studio_episode_stages
                               WHERE state='QUEUED'""").fetchall()
            for row in rows:
                job=db.execute("SELECT * FROM jobs WHERE job_id=?",
                               (row["job_id"],)).fetchone()
                if job is None or job["kind"] != row["stage"]:
                    raise StageLedgerError("Stage has inconsistent queued job lineage.")
                if job["state"] in ("FAILED","CANCELLED"):
                    state="BLOCKED"; artifact=None
                elif job["state"]=="COMPLETED":
                    receipt=json.loads(job["result_json"] or "{}")
                    expected,typ=STAGES[row["stage"]]
                    valid=(receipt.get("status")==expected and
                           receipt.get("artifact_type")==typ and
                           receipt.get("publication_approved") is False and
                           isinstance(receipt.get("artifact_sha256"),str) and
                           SHA.fullmatch(receipt["artifact_sha256"]))
                    state="PENDING_QA" if valid else "BLOCKED"
                    artifact=receipt.get("artifact_sha256") if valid else None
                else:
                    continue
                db.execute("""UPDATE studio_episode_stages
                    SET state=?,artifact_sha256=?,updated_at=?
                    WHERE series_id=? AND ordinal=? AND stage=?""",
                    (state,artifact,time.time(),row["series_id"],row["ordinal"],
                     row["stage"]))
                changed+=1
        return changed

    def approve(self, series_id: str, ordinal: int, stage: str,
                artifact_sha256: str, note: str) -> None:
        if stage not in STAGES or not isinstance(artifact_sha256,str) or not SHA.fullmatch(artifact_sha256):
            raise StageLedgerError("Exact stage and artifact SHA required.")
        if not isinstance(note,str) or not 10<=len(note.strip())<=500:
            raise StageLedgerError("Document owner's audiovisual/source QA.")
        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT state,artifact_sha256
                FROM studio_episode_stages WHERE series_id=? AND ordinal=? AND stage=?""",
                (series_id,ordinal,stage)).fetchone()
            if row is None or row["state"]!="PENDING_QA" or row["artifact_sha256"]!=artifact_sha256:
                raise StageLedgerError("Matching verified job receipt awaiting owner QA required.")
            db.execute("""UPDATE studio_episode_stages SET state='QA_APPROVED',
               owner_note=?,updated_at=? WHERE series_id=? AND ordinal=? AND stage=?""",
               (note.strip(),time.time(),series_id,ordinal,stage))

    def retry_blocked(self, series_id: str, ordinal: int,
                      stage: str, reason: str) -> None:
        if stage not in STAGES or not isinstance(reason,str) or not 10<=len(reason.strip())<=500:
            raise StageLedgerError("Manual retry requires specific stage and reason.")
        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT state FROM studio_episode_stages
                WHERE series_id=? AND ordinal=? AND stage=?""",
                (series_id,ordinal,stage)).fetchone()
            if row is None or row["state"]!="BLOCKED":
                raise StageLedgerError("Only blocked work can be retried.")
            if stage=="voice_synthesize" and db.execute("""SELECT 1
                FROM studio_episode_stages WHERE series_id=? AND ordinal=?
                  AND stage='ltx_animate'""",(series_id,ordinal)).fetchone():
                raise StageLedgerError("Do not change voice with an existing downstream LTX job.")
            db.execute("""UPDATE studio_episode_stages SET state='RESET_FOR_RETRY',
                job_id=NULL,attempt=attempt+1,artifact_sha256=NULL,
                owner_note=?,updated_at=? WHERE series_id=? AND ordinal=? AND stage=?""",
                (reason.strip(),time.time(),series_id,ordinal,stage))

    def snapshot(self) -> list[dict]:
        with self.queue._connection() as db:
            rows=db.execute("""SELECT series_id,ordinal,stage,state,
                    artifact_sha256,job_id,attempt,updated_at
                    FROM studio_episode_stages
                    ORDER BY series_id,ordinal,stage""").fetchall()
            return [dict(row) for row in rows]
