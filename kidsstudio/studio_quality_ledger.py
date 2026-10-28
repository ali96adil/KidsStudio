"""Studio Brain M7 per-episode QA evidence and owner acceptance gate.

Technical FFmpeg reports are local evidence; a separate explicit owner review
attests subjective criteria. Neither step publishes video. All records bind to
one exact completed render job and its unchanged media SHA256.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import time

from .episode_assembly import digest
from .episode_quality import CHECKS

SHA=re.compile(r"^[a-f0-9]{64}$")
CRITERIA=(
    "learning_objective", "age_appropriate_pedagogy", "language_pronunciation",
    "character_consistency", "lip_sync_and_motion", "audio_mix",
    "child_safety", "originality_and_attribution", "music_voice_visual_rights",
    "accessibility_and_subtitles", "full_episode_watch"
)


class QualityGateError(ValueError):
    """Quality result cannot be trusted or episode has unmet acceptance gates."""


def _private_json(file: str | Path, limit: int = 150_000) -> tuple[dict, str]:
    source=Path(file).expanduser().resolve()
    if not source.is_file() or not 0 < source.stat().st_size <= limit:
        raise QualityGateError("Owner supplied report missing or oversized.")
    if any((p/".git").exists() for p in (source.parent,*source.parents)):
        raise QualityGateError("Original private reports may not live in Git.")
    try:
        body=json.loads(source.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise QualityGateError("Invalid private QA JSON file.") from exc
    if not isinstance(body,dict):
        raise QualityGateError("QA file must be a JSON object.")
    return body,digest(source)


class QualityLedger:
    def __init__(self, queue):
        self.queue=queue

    def initialize(self) -> None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_quality_reviews(
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                render_job_id TEXT NOT NULL, media_sha256 TEXT NOT NULL,
                tech_report_sha256 TEXT NOT NULL,
                review_report_sha256 TEXT, checks_passed INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL, created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY(series_id,ordinal,render_job_id),
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_episodes(series_id,ordinal)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_quality_audit(
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                render_job_id TEXT NOT NULL,
                event TEXT NOT NULL, created_at REAL NOT NULL
            )""")

    @staticmethod
    def _current_render(db: sqlite3.Connection, series_id: str,
                        ordinal: int) -> tuple[str,str]:
        ep=db.execute("""SELECT state,render_job_id FROM studio_episodes
                WHERE series_id=? AND ordinal=?""",(series_id,ordinal)).fetchone()
        if ep is None or ep["state"]!="RENDERED_QA_PENDING" or not ep["render_job_id"]:
            raise QualityGateError("Only an actually completed, QA-pending episode is eligible.")
        job=db.execute("""SELECT kind,state,result_json FROM jobs
            WHERE job_id=?""",(ep["render_job_id"],)).fetchone()
        if job is None or job["kind"] not in ("godot_render","episode_assemble") or job["state"]!="COMPLETED":
            raise QualityGateError("Exact completed media job receipt required.")
        result=json.loads(job["result_json"] or "{}")
        sha=result.get("artifact_sha256")
        if (result.get("result_status",result.get("status"))!="VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW"
                or result.get("artifact_type")!="mp4"
                or not isinstance(sha,str) or not SHA.fullmatch(sha)
                or result.get("publication_approved") is not False):
            raise QualityGateError("Media receipt cannot establish QA lineage.")
        return ep["render_job_id"],sha

    @staticmethod
    def _audit(db, series_id,ordinal,job_id,event):
        db.execute("""INSERT INTO studio_quality_audit
            (series_id,ordinal,render_job_id,event,created_at)
            VALUES (?,?,?,?,?)""",(series_id,ordinal,job_id,event,time.time()))

    def register_technical(self, series_id: str, ordinal: int, report_file: str | Path) -> None:
        report, report_sha=_private_json(report_file)
        if set(report)!={
            "schema_version","status","media_sha256","expected_media_sha256",
            "file_bytes","duration_seconds","checks","subjective_checks_performed",
            "rights_verified","publishing_approved"}:
            raise QualityGateError("Unknown or missing technical QA report fields.")
        checks=report["checks"]
        if (report["schema_version"]!=1 or
            report["status"]!="TECH_PASS_OWNER_REVIEW_PENDING" or
            not isinstance(checks,dict) or set(checks)!=set(CHECKS) or
            not all(v is True for v in checks.values()) or
            report["subjective_checks_performed"] is not False or
            report["rights_verified"] is not False or
            report["publishing_approved"] is not False or
            not isinstance(report["file_bytes"],int) or report["file_bytes"]<=0 or
            type(report["duration_seconds"]) not in (int,float) or
            not 2<=report["duration_seconds"]<=900):
            raise QualityGateError("Technical evidence incomplete or marked as subjective approval.")
        with self.queue._connection(write=True) as db:
            job_id, media_sha=self._current_render(db,series_id,ordinal)
            if (report["media_sha256"] != media_sha or
                report["expected_media_sha256"] != media_sha):
                raise QualityGateError("Technical evidence references the wrong rendered MP4.")
            prior=db.execute("""SELECT 1 FROM studio_quality_reviews
                WHERE series_id=? AND ordinal=? AND render_job_id=?""",
                (series_id,ordinal,job_id)).fetchone()
            if prior:
                raise QualityGateError("This render already has QA evidence; never overwrite it.")
            now=time.time()
            db.execute("""INSERT INTO studio_quality_reviews
                (series_id,ordinal,render_job_id,media_sha256,tech_report_sha256,
                 state,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (series_id,ordinal,job_id,media_sha,report_sha,
                 "TECH_PASSED_WAITING_HUMAN",now,now))
            self._audit(db,series_id,ordinal,job_id,"TECHNICAL_REPORT_REGISTERED")

    def submit_owner_review(self, series_id: str, ordinal: int,
                            report_file: str | Path) -> None:
        review, review_sha=_private_json(report_file)
        if set(review)!={"schema_version","media_sha256","reviewer_role",
                         "criteria","summary"}:
            raise QualityGateError("Unexpected human QA form format.")
        if (review["schema_version"]!=1 or review["reviewer_role"]!="owner"
                or not isinstance(review["summary"],str) or
                not 25<=len(review["summary"].strip())<=2000):
            raise QualityGateError("Explicit owner assessment summary required.")
        criteria=review["criteria"]
        if not isinstance(criteria,dict) or set(criteria)!=set(CRITERIA):
            raise QualityGateError("All educational, artistic and rights criteria required.")
        for name in CRITERIA:
            row=criteria[name]
            if (not isinstance(row,dict) or set(row)!={"decision","evidence"} or
                row["decision"] not in ("PASS","NEEDS_FIX") or not isinstance(row["evidence"],str)
                or not 20<=len(row["evidence"].strip())<=800):
                raise QualityGateError(f"Owner has not passed/documented: {name}")
        with self.queue._connection(write=True) as db:
            job_id,media_sha=self._current_render(db,series_id,ordinal)
            row=db.execute("""SELECT state FROM studio_quality_reviews
                WHERE series_id=? AND ordinal=? AND render_job_id=?""",
                (series_id,ordinal,job_id)).fetchone()
            if row is None or row["state"]!="TECH_PASSED_WAITING_HUMAN":
                raise QualityGateError("A matching unmodified technical QA report is required first.")
            if review["media_sha256"]!=media_sha:
                raise QualityGateError("Human review references the wrong MP4.")
            passed=sum(1 for item in criteria.values() if item["decision"]=="PASS")
            decision=("READY_FOR_OWNER_EPISODE_APPROVAL"
                      if passed==len(CRITERIA) else "CHANGES_REQUESTED")
            db.execute("""UPDATE studio_quality_reviews
                SET state=?,review_report_sha256=?,checks_passed=?,updated_at=?
                WHERE series_id=? AND ordinal=? AND render_job_id=?""",
                (decision,review_sha,passed,time.time(),series_id,ordinal,job_id))
            if decision=="CHANGES_REQUESTED":
                failed="، ".join(k for k in CRITERIA
                                if criteria[k]["decision"]=="NEEDS_FIX")
                db.execute("""INSERT INTO studio_series_notes
                    (series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
                    (series_id,ordinal,"M7 QA NEEDS FIX: "+failed+
                     " — "+review["summary"].strip()[:500],time.time()))
            self._audit(db,series_id,ordinal,job_id,
                        "OWNER_QA_READY" if passed==len(CRITERIA)
                        else "OWNER_REQUESTED_CHANGES")

    def snapshot(self) -> list[dict]:
        with self.queue._connection() as db:
            return [dict(row) for row in db.execute("""SELECT q.series_id,
                q.ordinal,q.render_job_id,q.state,q.checks_passed,
                q.updated_at
                FROM studio_quality_reviews q
                JOIN studio_episodes e ON
                  (e.series_id=q.series_id AND e.ordinal=q.ordinal AND
                   e.render_job_id=q.render_job_id)
                ORDER BY q.series_id,q.ordinal""")]
