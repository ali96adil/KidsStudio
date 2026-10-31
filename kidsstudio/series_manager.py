"""Persistent, series-first, owner-gated production planning for Studio Brain.

This module NEVER calls an LLM, renderer, uploader, or external service.
It uses the existing local SQLite queue and its atomic job/audit contract.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from typing import Any
from uuid import uuid4

from .studio_queue import StudioQueue, _json_object

IDENT = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
RECIPE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class SeriesError(ValueError):
    """Rejected syllabus or unsafe production-state transition."""


def scene_script_fingerprint(scenes: Any) -> str:
    """Stable SHA of the ordered, immutable M13 scene identity set."""
    data=[[row["scene"], row["script_sha256"]] for row in scenes]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False,
        separators=(",",":"), allow_nan=False).encode("utf-8")).hexdigest()


class SeriesManager:
    def __init__(self, queue: StudioQueue):
        self.queue = queue

    def initialize(self) -> None:
        """Additive schema migration on an EXISTING StudioQueue SQLite file."""
        statements = """
            CREATE TABLE IF NOT EXISTS studio_series (
                series_id TEXT PRIMARY KEY, title TEXT NOT NULL,
                language TEXT NOT NULL, state TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS only_one_active_series
                ON studio_series(state) WHERE state='ACTIVE';
            CREATE TABLE IF NOT EXISTS studio_episodes (
                series_id TEXT NOT NULL REFERENCES studio_series(series_id),
                ordinal INTEGER NOT NULL, title TEXT NOT NULL,
                objective TEXT NOT NULL, state TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                draft_job_id TEXT, review_job_id TEXT,
                source_sha256 TEXT, owner_review_note TEXT,
                render_job_id TEXT, render_attempt INTEGER NOT NULL DEFAULT 1,
                updated_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal)
            );
            CREATE TABLE IF NOT EXISTS studio_series_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id TEXT NOT NULL REFERENCES studio_series(series_id),
                ordinal INTEGER, note TEXT NOT NULL, created_at REAL NOT NULL,
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_episodes(series_id,ordinal)
            );
            CREATE TABLE IF NOT EXISTS studio_series_audit (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id TEXT NOT NULL, ordinal INTEGER,
                action TEXT NOT NULL, created_at REAL NOT NULL
            );
        """
        with self.queue._connection(write=True) as db:
            for statement in statements.split(";"):
                if statement.strip():
                    db.execute(statement)

    @staticmethod
    def _audit(db: sqlite3.Connection, sid: str,
               ordinal: int | None, action: str) -> None:
        db.execute("""INSERT INTO studio_series_audit
            (series_id,ordinal,action,created_at) VALUES (?,?,?,?)""",
            (sid,ordinal,action,time.time()))

    @staticmethod
    def _validate(sid: str, title: str, language: str,
                  lessons: list[dict[str,str]]) -> None:
        if not isinstance(sid,str) or not IDENT.fullmatch(sid):
            raise SeriesError("Invalid stable series identifier.")
        if not isinstance(title,str) or not 1 <= len(title.strip()) <= 120:
            raise SeriesError("Invalid series title.")
        if language not in ("ar","en"):
            raise SeriesError("Only ar/en are supported.")
        if not isinstance(lessons,list) or not 1 <= len(lessons) <= 120:
            raise SeriesError("Plan requires 1..120 ordered lessons.")
        for lesson in lessons:
            if not isinstance(lesson,dict) or set(lesson) != {"title","objective"}:
                raise SeriesError("Each lesson requires title and objective.")
            if any(not isinstance(v,str) or not 1 <= len(v.strip()) <= 160
                   for v in lesson.values()):
                raise SeriesError("Lesson title/objective must be 1..160 chars.")

    def create_series(self, series_id: str, title: str, language: str,
                      lessons: list[dict[str,str]], *, activate: bool = False) -> None:
        self._validate(series_id,title,language,lessons)
        now=time.time()
        try:
            with self.queue._connection(write=True) as db:
                db.execute("INSERT INTO studio_series VALUES (?,?,?,?,?)",
                           (series_id,title.strip(),language,
                            "ACTIVE" if activate else "PLANNED",now))
                for ordinal,lesson in enumerate(lessons,1):
                    db.execute("""INSERT INTO studio_episodes
                        (series_id,ordinal,title,objective,state,updated_at)
                        VALUES (?,?,?,?,?,?)""",
                        (series_id,ordinal,lesson["title"].strip(),
                         lesson["objective"].strip(),"PLANNED",now))
                self._audit(db,series_id,None,"SERIES_CREATED")
        except sqlite3.IntegrityError as exc:
            raise SeriesError("Series exists or another series is ACTIVE.") from exc

    def activate(self, series_id: str) -> None:
        with self.queue._connection(write=True) as db:
            row=db.execute("SELECT state FROM studio_series WHERE series_id=?",
                           (series_id,)).fetchone()
            if row is None or row["state"] == "COMPLETED":
                raise SeriesError("Unknown/completed series.")
            if db.execute("""SELECT 1 FROM studio_series
                  WHERE state='ACTIVE' AND series_id<>?""",(series_id,)).fetchone():
                raise SeriesError("Pause or finish the current series first.")
            db.execute("UPDATE studio_series SET state='ACTIVE' WHERE series_id=?",
                       (series_id,))
            self._audit(db,series_id,None,"SERIES_ACTIVATED")

    def pause(self, series_id: str, reason: str) -> None:
        if not isinstance(reason,str) or not 5 <= len(reason.strip()) <= 500:
            raise SeriesError("Pause requires a meaningful reason.")
        with self.queue._connection(write=True) as db:
            row=db.execute("SELECT state FROM studio_series WHERE series_id=?",
                           (series_id,)).fetchone()
            if row is None or row["state"] != "ACTIVE":
                raise SeriesError("Only the active series may be paused.")
            db.execute("UPDATE studio_series SET state='PAUSED' WHERE series_id=?",
                       (series_id,))
            db.execute("""INSERT INTO studio_series_notes
                (series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
                (series_id,None,"PAUSED: "+reason.strip(),time.time()))
            self._audit(db,series_id,None,"SERIES_PAUSED")

    def note(self, series_id: str, message: str,
             ordinal: int | None = None) -> None:
        if not isinstance(message,str) or not 1 <= len(message.strip()) <= 1000:
            raise SeriesError("Note must be 1..1000 chars.")
        with self.queue._connection(write=True) as db:
            db.execute("""INSERT INTO studio_series_notes
                (series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
                (series_id,ordinal,message.strip(),time.time()))
            self._audit(db,series_id,ordinal,"NOTE_ADDED")

    def plan_drafts(self, *, limit: int = 3) -> list[dict[str,Any]]:
        """Atomic, bounded idle-work planner: enqueues only, executes nothing."""
        if type(limit) is not int or not 1 <= limit <= 3:
            raise SeriesError("Idle backlog capacity is 1..3.")
        with self.queue._connection(write=True) as db:
            if db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()[0]:
                return []
            active=db.execute("""SELECT series_id,language FROM studio_series
                                 WHERE state='ACTIVE'""").fetchone()
            if active is None:
                return []
            sid,language=active["series_id"],active["language"]
            occupied=db.execute("""SELECT COUNT(*) FROM studio_episodes
                WHERE series_id=? AND state NOT IN
                      ('PLANNED','EPISODE_APPROVED')""",(sid,)).fetchone()[0]
            rows=db.execute("""SELECT * FROM studio_episodes
                WHERE series_id=? AND state='PLANNED'
                ORDER BY ordinal LIMIT ?""",(sid,max(0,limit-occupied))).fetchall()
            made=[]
            for ep in rows:
                ordinal=ep["ordinal"]
                key=f"series:{sid}:episode:{ordinal}:draft:v{ep['revision']}"
                topic=(f"Series {sid}, episode {ordinal}: {ep['title']}. "
                       f"Learning objective: {ep['objective']}. "
                       "Continue this curriculum in order.")
                request={"language":language,"topic":topic,"auto_review":True}
                # M15 learning may influence a FUTURE original draft, never
                # change approved episodes or bypass independent editorial QA.
                if db.execute("""SELECT 1 FROM sqlite_master WHERE
                    type='table' AND name='studio_learning_proposals'""").fetchone():
                    adoption=db.execute("""SELECT proposal_id,feature_name,
                        winning_style FROM studio_learning_proposals
                        WHERE series_id=? AND status='ADOPT_FOR_FUTURE_EXPERIMENT'
                        ORDER BY decided_at DESC LIMIT 1""",(sid,)).fetchone()
                    if adoption:
                        request["learning_experiment"]={
                            "proposal_id":adoption["proposal_id"],
                            "feature":adoption["feature_name"],
                            "style":adoption["winning_style"]
                        }
                payload=_json_object(request,"payload")
                if len(topic)>400:
                    raise SeriesError("Lesson topic exceeds worker input size.")
                prior=db.execute("SELECT * FROM jobs WHERE request_key=?",
                                 (key,)).fetchone()
                if prior:
                    if prior["kind"]!="script_draft" or prior["payload"]!=payload:
                        raise SeriesError("Conflicting queue idempotency key.")
                    job_id=prior["job_id"]
                else:
                    now=self.queue.clock()
                    job_id=uuid4().hex
                    db.execute("""INSERT INTO jobs
                        (job_id,request_key,kind,payload,state,max_attempts,
                         available_at,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (job_id,key,"script_draft",payload,"QUEUED",2,now,now,now))
                    self.queue._event(db,job_id,"ENQUEUED",{"kind":"script_draft"})
                db.execute("""UPDATE studio_episodes
                    SET state='DRAFT_QUEUED',draft_job_id=?,updated_at=?
                    WHERE series_id=? AND ordinal=?""",
                    (job_id,time.time(),sid,ordinal))
                self._audit(db,sid,ordinal,"DRAFT_ENQUEUED")
                made.append({"series_id":sid,"ordinal":ordinal,"job_id":job_id})
            return made

    def reconcile(self,series_id: str|None=None,
                  ordinal: int|None=None) -> int:
        """Reconcile receipts for all episodes or one explicit production."""
        if (series_id is None)!=(ordinal is None):
            raise SeriesError("Scoped reconcile needs both series and episode.")
        if series_id is not None and (
            not isinstance(series_id,str) or not IDENT.fullmatch(series_id) or
            type(ordinal) is not int or not 1<=ordinal<=120):
            raise SeriesError("Invalid episode selector for reconciliation.")
        changed=0
        with self.queue._connection(write=True) as db:
            rows=db.execute("""SELECT * FROM studio_episodes
                WHERE state IN ('DRAFT_QUEUED','REVIEW_QUEUED',
                                'RENDER_QUEUED')
                AND (? IS NULL OR series_id=?)
                AND (? IS NULL OR ordinal=?)""",
                (series_id,series_id,ordinal,ordinal)).fetchall()
            for ep in rows:
                media=ep["state"]=="RENDER_QUEUED"
                job_id=ep["render_job_id"] if media else ep["draft_job_id"]
                job=db.execute("SELECT * FROM jobs WHERE job_id=?",
                               (job_id,)).fetchone()
                if job is None:
                    raise SeriesError("Referenced queue job is missing.")
                state=ep["state"]
                child_id=ep["review_job_id"]
                digest=ep["source_sha256"]
                if job["state"] in ("FAILED","CANCELLED"):
                    state="BLOCKED"
                elif media and job["state"]=="COMPLETED":
                    result=json.loads(job["result_json"] or "{}")
                    state=("RENDERED_QA_PENDING" if
                        result.get("result_status", result.get("status"))=="VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW"
                        and result.get("artifact_type")=="mp4"
                        and isinstance(result.get("artifact_sha256"),str)
                        and DIGEST.fullmatch(result["artifact_sha256"])
                        and result.get("publication_approved") is False
                        else "BLOCKED")
                elif not media and job["state"]=="COMPLETED":
                    result=json.loads(job["result_json"] or "{}")
                    if (result.get("status")!="DRAFTED_UNREVIEWED" or
                        not isinstance(result.get("artifact_sha256"),str) or
                        not DIGEST.fullmatch(result["artifact_sha256"])):
                        state="BLOCKED"
                    else:
                        digest=result["artifact_sha256"]
                        child_id=result.get("next_review_job_id")
                        child=(db.execute("SELECT * FROM jobs WHERE job_id=?",
                                          (child_id,)).fetchone()
                               if isinstance(child_id,str) else None)
                        if child is None or child["kind"]!="editorial_review":
                            state="BLOCKED"
                        elif child["state"] in ("FAILED","CANCELLED"):
                            state="BLOCKED"
                        elif child["state"]=="COMPLETED":
                            review=json.loads(child["result_json"] or "{}")
                            state=("OWNER_SCRIPT_REVIEW" if
                                review.get("status")=="EDITORIAL_REVIEW_UNVERIFIED"
                                and review.get("publication_approved") is False
                                else "BLOCKED")
                        else:
                            state="REVIEW_QUEUED"
                if (state!=ep["state"] or child_id!=ep["review_job_id"]
                    or digest!=ep["source_sha256"]):
                    db.execute("""UPDATE studio_episodes
                        SET state=?,review_job_id=?,source_sha256=?,updated_at=?
                        WHERE series_id=? AND ordinal=?""",
                        (state,child_id,digest,time.time(),ep["series_id"],
                         ep["ordinal"]))
                    self._audit(db,ep["series_id"],ep["ordinal"],"QUEUE_RECONCILED")
                    changed+=1
        return changed

    def approve_script(self, series_id: str, ordinal: int,
                       source_sha256: str, review_note: str) -> None:
        if not isinstance(source_sha256,str) or not DIGEST.fullmatch(source_sha256):
            raise SeriesError("Exact source SHA256 required.")
        if not isinstance(review_note,str) or not 5<=len(review_note.strip())<=500:
            raise SeriesError("Owner review note required.")
        with self.queue._connection(write=True) as db:
            ep=db.execute("""SELECT * FROM studio_episodes
                WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
            if (ep is None or ep["state"]!="OWNER_SCRIPT_REVIEW" or
                ep["source_sha256"]!=source_sha256):
                raise SeriesError("Independent review and matching draft required.")
            db.execute("""UPDATE studio_episodes SET state='SCRIPT_APPROVED',
                owner_review_note=?,updated_at=?
                WHERE series_id=? AND ordinal=?""",
                (review_note.strip(),time.time(),series_id,ordinal))
            self._audit(db,series_id,ordinal,"SCRIPT_APPROVED_BY_OWNER")

    def queue_render(self, series_id: str, ordinal: int,
                     recipe_id: str, *, media_kind: str = "godot_render",
                     catalogue_sha256: str | None = None,
                     orchestrator_plan_sha256: str | None = None,
                     require_orchestrator_binding: bool = False) -> str:
        """Atomically fence M32 scene/catalogue pins before render enqueue.

        The optional M50 guards are for StudioOrchestrator. Existing explicit
        owner queue calls keep their pre-existing requirements.
        """
        if not isinstance(recipe_id,str) or not RECIPE.fullmatch(recipe_id):
            raise SeriesError("Use a pinned local recipe identifier.")
        if media_kind not in ("godot_render", "episode_assemble"):
            raise SeriesError("Unsupported media kind.")
        if orchestrator_plan_sha256 is not None and (
            media_kind != "episode_assemble" or
            not isinstance(orchestrator_plan_sha256,str) or
            not DIGEST.fullmatch(orchestrator_plan_sha256)):
            raise SeriesError("M50 requires exact M32 orchestration plan SHA.")
        if require_orchestrator_binding and orchestrator_plan_sha256 is None:
            raise SeriesError("M50 deferred catalogue requires orchestrator pin.")
        with self.queue._connection(write=True) as db:
            paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
            if not paused or paused["paused"]:
                raise SeriesError("Studio queue paused; no assembly or render dispatch.")
            ep=db.execute("""SELECT * FROM studio_episodes
                WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
            if ep is None or ep["state"]!="SCRIPT_APPROVED":
                raise SeriesError("Owner-approved script required before rendering.")
            # When M6 staged production was started for this episode, a
            # standalone assembly requires independently owner-approved voice
            # AND animation receipts. Legacy pre-rendered clips remain possible
            # only if no stage production was ever opened for this episode.
            if media_kind=="episode_assemble" and db.execute("""SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='studio_episode_stages'""").fetchone():
                existing=db.execute("""SELECT stage,state,script_sha256
                    FROM studio_episode_stages WHERE series_id=? AND ordinal=?""",
                    (series_id,ordinal)).fetchall()
                if existing and (
                    len(existing)!=2 or
                    {r["stage"] for r in existing}!={"voice_synthesize","ltx_animate"} or
                    any(r["state"]!="QA_APPROVED" or
                        r["script_sha256"]!=ep["source_sha256"] for r in existing)
                ):
                    raise SeriesError("Independent owner-approved voice and LTX required before assembly.")
            requires_frozen_catalogue=False
            if db.execute("""SELECT 1 FROM sqlite_master WHERE
                type='table' AND name='studio_scene_plans'""").fetchone():
                scene_plan=db.execute("""SELECT plan_sha256,episode_script_sha256
                    FROM studio_scene_plans WHERE series_id=? AND ordinal=?""",
                    (series_id,ordinal)).fetchone()
                if scene_plan:
                    requires_frozen_catalogue=True
                    if media_kind!="episode_assemble":
                        raise SeriesError("Scene plan requires episode assembly.")
                    from .studio_scenes import assert_scenes_ready, SceneError
                    try:
                        assert_scenes_ready(db,series_id,ordinal,ep["source_sha256"])
                    except SceneError as exc:
                        raise SeriesError("Scene production still needs review.") from exc
            if requires_frozen_catalogue and (
                not isinstance(catalogue_sha256,str) or
                not DIGEST.fullmatch(catalogue_sha256)):
                raise SeriesError("M14 multi-scene owner catalogue SHA256 is mandatory.")
            if not requires_frozen_catalogue and catalogue_sha256 is not None:
                raise SeriesError("Catalogue SHA is only supported on M13 multi-scene recipes.")
            # M51: a pinned M32 episode cannot use the older series-cli
            # queue-render route. The exact recipe, catalogue policy and
            # original scene IDs are checked atomically, not supplied by CLI.
            has_m32=db.execute("""SELECT 1 FROM sqlite_master WHERE
                type='table' AND name='studio_orchestrator_plans'""").fetchone()
            pinned=(db.execute("""SELECT plan_sha256,script_sha256,
                scene_plan_sha256 FROM studio_orchestrator_plans
                WHERE series_id=? AND ordinal=?""",
                (series_id,ordinal)).fetchone() if has_m32 else None)
            if pinned and orchestrator_plan_sha256 is None:
                raise SeriesError("M51 orchestrated episode must use studio-orchestrator tick.")
            if orchestrator_plan_sha256 is not None:
                active=db.execute("""SELECT state FROM studio_series
                    WHERE series_id=?""",(series_id,)).fetchone()
                if (not requires_frozen_catalogue or not pinned or not scene_plan
                    or not active or active["state"]!="ACTIVE"
                    or pinned["plan_sha256"]!=orchestrator_plan_sha256
                    or pinned["script_sha256"]!=ep["source_sha256"]
                    or pinned["scene_plan_sha256"]!=scene_plan["plan_sha256"]
                    or scene_plan["episode_script_sha256"]!=ep["source_sha256"]):
                    raise SeriesError("M50 pinned plan changed before atomic enqueue.")
                if not db.execute("""SELECT 1 FROM sqlite_master WHERE
                    type='table' AND name='studio_orchestrator_render_contracts'""").fetchone():
                    raise SeriesError("M51 immutable render contract schema missing.")
                contract=db.execute("""SELECT plan_sha256,recipe_id,
                    catalogue_marker,scene_scripts_sha256
                    FROM studio_orchestrator_render_contracts
                    WHERE series_id=? AND ordinal=?""",
                    (series_id,ordinal)).fetchone()
                scenes=db.execute("""SELECT scene,script_sha256 FROM studio_scenes
                    WHERE series_id=? AND ordinal=? ORDER BY scene""",
                    (series_id,ordinal)).fetchall()
                if (not contract or
                    contract["plan_sha256"]!=orchestrator_plan_sha256 or
                    contract["recipe_id"]!=recipe_id or
                    not scenes or
                    contract["scene_scripts_sha256"]!=scene_script_fingerprint(scenes)):
                    raise SeriesError("M51 immutable render recipe/scene contract mismatch.")
                deferred=contract["catalogue_marker"]=="AFTER_SCENE_QA"
                if deferred!=require_orchestrator_binding:
                    raise SeriesError("M51 catalogue binding policy mismatch.")
                if not deferred and contract["catalogue_marker"]!=catalogue_sha256:
                    raise SeriesError("M51 pre-pinned catalogue differs from M32 plan.")
                if require_orchestrator_binding:
                    binding=db.execute("""SELECT plan_sha256,catalogue_sha256,
                        scene_set_sha256 FROM studio_orchestrator_assembly_bindings
                        WHERE series_id=? AND ordinal=?""",
                        (series_id,ordinal)).fetchone()
                    from .studio_scenes import assert_scenes_ready
                    ready=assert_scenes_ready(db,series_id,ordinal,
                                              ep["source_sha256"])
                    frozen=hashlib.sha256(json.dumps(
                        ready,sort_keys=True,ensure_ascii=False,
                        separators=(",",":"),allow_nan=False
                    ).encode("utf-8")).hexdigest()
                    if (not binding or
                        binding["plan_sha256"]!=orchestrator_plan_sha256 or
                        binding["catalogue_sha256"]!=catalogue_sha256 or
                        binding["scene_set_sha256"]!=frozen):
                        raise SeriesError("M50 catalogue/scene binding changed before enqueue.")
            key=(f"series:{series_id}:episode:{ordinal}:"
                 f"render:{media_kind}:a{ep['render_attempt']}:{ep['source_sha256'][:16]}")
            payload_data=({"recipe_id":recipe_id,
                           "script_sha256":ep["source_sha256"]}
                          if media_kind=="episode_assemble" else
                          {"recipe_id":recipe_id})
            if requires_frozen_catalogue:
                payload_data["catalogue_sha256"]=catalogue_sha256
            payload=_json_object(payload_data,"payload")
            prior=db.execute("SELECT * FROM jobs WHERE request_key=?",
                             (key,)).fetchone()
            if prior:
                if prior["kind"]!=media_kind or prior["payload"]!=payload:
                    raise SeriesError("Existing job has different recipe.")
                job_id=prior["job_id"]
            else:
                now=self.queue.clock()
                job_id=uuid4().hex
                db.execute("""INSERT INTO jobs
                    (job_id,request_key,kind,payload,state,max_attempts,
                     available_at,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (job_id,key,media_kind,payload,"QUEUED",1,now,now,now))
                self.queue._event(db,job_id,"ENQUEUED",{"kind":media_kind})
            db.execute("""UPDATE studio_episodes
                SET state='RENDER_QUEUED',render_job_id=?,updated_at=?
                WHERE series_id=? AND ordinal=?""",
                (job_id,time.time(),series_id,ordinal))
            self._audit(db,series_id,ordinal,"RENDER_ENQUEUED_BY_OWNER")
            return job_id

    def retry_blocked(self, series_id: str, ordinal: int,
                      reason: str) -> str:
        """Explicit owner retry: creates new idempotency generation, never auto-replays."""
        if not isinstance(reason,str) or not 10<=len(reason.strip())<=500:
            raise SeriesError("Owner must explain the retry.")
        with self.queue._connection(write=True) as db:
            ep=db.execute("""SELECT * FROM studio_episodes
                WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
            if ep is None or ep["state"]!="BLOCKED":
                raise SeriesError("Only a blocked episode can be reset.")
            if ep["render_job_id"]:
                state="SCRIPT_APPROVED"
                db.execute("""UPDATE studio_episodes SET state=?,render_job_id=NULL,
                    render_attempt=render_attempt+1,updated_at=?
                    WHERE series_id=? AND ordinal=?""",
                    (state,time.time(),series_id,ordinal))
            else:
                state="PLANNED"
                db.execute("""UPDATE studio_episodes
                    SET state=?,revision=revision+1,draft_job_id=NULL,
                    review_job_id=NULL,source_sha256=NULL,owner_review_note=NULL,
                    updated_at=? WHERE series_id=? AND ordinal=?""",
                    (state,time.time(),series_id,ordinal))
            db.execute("""INSERT INTO studio_series_notes
                (series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
                (series_id,ordinal,"OWNER RETRY: "+reason.strip(),time.time()))
            self._audit(db,series_id,ordinal,"BLOCKED_RESET_BY_OWNER")
            return state

    def approve_episode(self, series_id: str, ordinal: int,
                        review_note: str) -> None:
        if not isinstance(review_note,str) or not 10<=len(review_note.strip())<=600:
            raise SeriesError("Document audiovisual, curriculum and rights review.")
        with self.queue._connection(write=True) as db:
            ep=db.execute("""SELECT state FROM studio_episodes
                WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
            if ep is None or ep["state"]!="RENDERED_QA_PENDING":
                raise SeriesError("Rendered video must pass owner QA first.")
            qa_table=db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='studio_quality_reviews'""").fetchone()
            if qa_table:
                current=db.execute("""SELECT render_job_id FROM studio_episodes
                    WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
                qa=db.execute("""SELECT state,checks_passed FROM studio_quality_reviews
                    WHERE series_id=? AND ordinal=? AND render_job_id=?""",
                    (series_id,ordinal,current["render_job_id"])).fetchone()
                if qa is None or qa["state"]!="READY_FOR_OWNER_EPISODE_APPROVAL" or qa["checks_passed"]!=11:
                    raise SeriesError("Complete M7 technical, educational and rights QA required.")
            db.execute("""UPDATE studio_episodes
                SET state='EPISODE_APPROVED',owner_review_note=?,updated_at=?
                WHERE series_id=? AND ordinal=?""",
                (review_note.strip(),time.time(),series_id,ordinal))
            self._audit(db,series_id,ordinal,"EPISODE_APPROVED_INTERNAL_ONLY")

    def finalize_ai_private(self,series_id: str,ordinal: int) -> dict:
        """Internal readiness ONLY; owner decides after the PRIVATE upload."""
        with self.queue._connection(write=True) as db:
            ep=db.execute("""SELECT state,render_job_id,source_sha256 FROM
                studio_episodes WHERE series_id=? AND ordinal=?""",
                (series_id,ordinal)).fetchone()
            if not ep or ep["state"]!="RENDERED_QA_PENDING":
                raise SeriesError("Current completed MP4 awaiting independent AI QA required.")
            qa=db.execute("""SELECT * FROM studio_quality_reviews WHERE
                series_id=? AND ordinal=? AND render_job_id=?""",
                (series_id,ordinal,ep["render_job_id"])).fetchone()
            ai=db.execute("""SELECT * FROM studio_ai_final_reviews WHERE
                series_id=? AND ordinal=? AND render_job_id=?""",
                (series_id,ordinal,ep["render_job_id"])).fetchone()
            if (not qa or qa["state"]!="AI_INTERNAL_READY_PRIVATE_ONLY" or
                qa["checks_passed"]!=11 or not qa["tech_report_sha256"] or
                not ai or ai["status"]!="AI_INTERNAL_READY_PRIVATE_ONLY" or
                ai["script_sha256"]!=ep["source_sha256"] or
                ai["review_bundle_sha256"]!=qa["review_report_sha256"] or
                qa["media_sha256"]!=ai["media_sha256"]):
                raise SeriesError("Two independent AI reviews and all source evidence required.")
            db.execute("""UPDATE studio_episodes SET
                state='EPISODE_APPROVED',
                owner_review_note='AI_INTERNAL_PRIVATE_ONLY_NO_OWNER_VIDEO_REVIEW',
                updated_at=? WHERE series_id=? AND ordinal=?""",
                (self.queue.clock(),series_id,ordinal))
            self._audit(db,series_id,ordinal,
                        "M27_AI_INTERNAL_READY_OWNER_REVIEW_AFTER_PRIVATE_ONLY")
        return {"status":"AI_INTERNAL_READY_FOR_PRIVATE_UPLOAD",
                "owner_post_upload_review_required":True,
                "public_release_authorized":False}

    def complete_series(self, series_id: str) -> None:
        with self.queue._connection(write=True) as db:
            series=db.execute("""SELECT state FROM studio_series WHERE series_id=?""",
                              (series_id,)).fetchone()
            if series is None or series["state"]!="ACTIVE":
                raise SeriesError("Only an active series may be completed.")
            remaining=db.execute("""SELECT COUNT(*) FROM studio_episodes
                 WHERE series_id=? AND state!='EPISODE_APPROVED'""",
                 (series_id,)).fetchone()[0]
            if remaining:
                raise SeriesError(f"{remaining} episodes remain unapproved.")
            db.execute("UPDATE studio_series SET state='COMPLETED' WHERE series_id=?",
                       (series_id,))
            self._audit(db,series_id,None,"SERIES_INTERNAL_PRODUCTION_COMPLETED")

    def snapshot(self) -> dict[str,Any]:
        """Read-only dashboard data; no script text, model tokens or media."""
        with self.queue._connection() as db:
            series=[dict(r) for r in db.execute("""SELECT s.*,
                (SELECT COUNT(*) FROM studio_episodes e WHERE e.series_id=s.series_id)
                    AS total,
                (SELECT COUNT(*) FROM studio_episodes e WHERE e.series_id=s.series_id
                   AND e.state='EPISODE_APPROVED') AS episodes_approved
                FROM studio_series s ORDER BY created_at,series_id""")]
            episodes=[dict(r) for r in db.execute("""SELECT series_id,ordinal,
                title,objective,state,revision,draft_job_id,review_job_id,
                render_job_id,updated_at FROM studio_episodes
                ORDER BY series_id,ordinal""")]
            notes=[dict(r) for r in db.execute("""SELECT note_id,series_id,ordinal,
                note,created_at FROM studio_series_notes
                ORDER BY note_id DESC LIMIT 100""")]
            counts={r["state"]:r["n"] for r in db.execute(
                "SELECT state,COUNT(*) AS n FROM jobs GROUP BY state")}
            return {"series":series,"episodes":episodes,"notes":notes,
                    "queue_counts":counts}
