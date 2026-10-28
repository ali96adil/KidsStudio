"""M24: durable owner decisions on *already uploaded* PRIVATE YouTube previews.

No YouTube integration or visibility verification exists here. The owner records
an external upload after it happened. Decisions and timestamped comments are
per *exact video ID + render job + master SHA* and never authorize a different
upload. All changes are owner-only local operations, not AI agent actions.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any

from .studio_queue import StudioQueue
from .series_manager import IDENT, DIGEST

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
CATEGORIES = frozenset({"audio", "animation", "text", "education",
                        "timing", "visual", "thumbnail", "other"})
DECISIONS = frozenset({"APPROVE", "APPROVE_WITH_NOTES", "REQUEST_CHANGES"})
MAX_NOTES = 1200


class PreviewReviewError(ValueError):
    """Untrusted upload lineage, invalid note or unsafe review transition."""


def _note(note: str, *, required: bool) -> str:
    if not isinstance(note, str):
        raise PreviewReviewError("Note must be a string.")
    value = note.strip()
    if (required and not value) or len(value) > MAX_NOTES or (
        value and len(value) < 5
    ):
        raise PreviewReviewError("Note must have 5..1200 characters when supplied.")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise PreviewReviewError("Control characters are forbidden in feedback.")
    return value


def _target(series_id: str, episode_number: int) -> None:
    if (not isinstance(series_id, str) or not IDENT.fullmatch(series_id)
            or type(episode_number) is not int
            or not 1 <= episode_number <= 120):
        raise PreviewReviewError("Valid series/episode required.")


def _video(video_id: str) -> None:
    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        raise PreviewReviewError("Exact 11-character YouTube video ID required.")


class PreviewReview:
    def __init__(self, queue: StudioQueue):
        self.queue = queue

    def initialize(self) -> None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_private_previews (
                video_id TEXT PRIMARY KEY,
                series_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                render_job_id TEXT NOT NULL,
                master_sha256 TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN (
                    'PRIVATE_AWAITING_OWNER_REVIEW', 'APPROVED',
                    'APPROVED_WITH_NOTES', 'REVISION_REQUESTED')),
                version INTEGER NOT NULL,
                claimed_visibility TEXT NOT NULL CHECK(claimed_visibility='PRIVATE'),
                platform_privacy_verified INTEGER NOT NULL DEFAULT 0,
                recorded_at REAL NOT NULL,
                reviewed_at REAL,
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_episodes(series_id,ordinal),
                UNIQUE(series_id,ordinal,version)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_private_preview_feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                category TEXT NOT NULL,
                second INTEGER,
                note TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('COMMENT','DECISION')),
                decision TEXT,
                agent_action TEXT NOT NULL CHECK(agent_action IN (
                    'NONE','CONSIDER_NEXT_EPISODE','TRIAGE_REVISION')),
                created_at REAL NOT NULL,
                FOREIGN KEY(video_id) REFERENCES studio_private_previews(video_id)
            )""")

    @staticmethod
    def _current_render(db: sqlite3.Connection, sid: str,
                        ordinal: int) -> tuple[str, str]:
        row=db.execute("""SELECT state,render_job_id
            FROM studio_episodes WHERE series_id=? AND ordinal=?""",
            (sid,ordinal)).fetchone()
        if not row or row["state"]!="EPISODE_APPROVED" or not row["render_job_id"]:
            raise PreviewReviewError("Only final internally approved episode can be previewed.")
        job=db.execute("SELECT kind,state,result_json FROM jobs WHERE job_id=?",
                       (row["render_job_id"],)).fetchone()
        if not job or job["kind"] not in ("episode_assemble","godot_render") or job["state"]!="COMPLETED":
            raise PreviewReviewError("Current final render has no completed job.")
        try: receipt=json.loads(job["result_json"] or "{}")
        except (TypeError,ValueError):
            raise PreviewReviewError("Render receipt malformed.") from None
        sha=receipt.get("artifact_sha256")
        if (receipt.get("status")!="VIDEO_RENDERED_PENDING_FINAL_VISUAL_REVIEW"
                or receipt.get("artifact_type")!="mp4" or
                not isinstance(sha,str) or not DIGEST.fullmatch(sha)
                or receipt.get("publication_approved") is not False):
            raise PreviewReviewError("Exact private master receipt required.")
        if db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                     AND name='studio_quality_reviews'""").fetchone():
            qa=db.execute("""SELECT state,media_sha256,checks_passed,review_report_sha256 FROM
                studio_quality_reviews WHERE series_id=? AND ordinal=?
                AND render_job_id=?""",(sid,ordinal,row["render_job_id"])).fetchone()
            if (not qa or qa["state"] not in (
                    "READY_FOR_OWNER_EPISODE_APPROVAL",
                    "AI_INTERNAL_READY_PRIVATE_ONLY") or
                    qa["media_sha256"]!=sha or qa["checks_passed"]!=11):
                raise PreviewReviewError("Current M7/M27 technical review approval missing.")
            if qa["state"]=="AI_INTERNAL_READY_PRIVATE_ONLY":
                ai=db.execute("""SELECT status,media_sha256,
                    review_bundle_sha256 FROM studio_ai_final_reviews
                    WHERE series_id=? AND ordinal=? AND render_job_id=?""",
                    (sid,ordinal,row["render_job_id"])).fetchone()
                if (not ai or ai["status"]!="AI_INTERNAL_READY_PRIVATE_ONLY" or
                    ai["media_sha256"]!=sha or
                    ai["review_bundle_sha256"]!=qa["review_report_sha256"]):
                    raise PreviewReviewError("Exact two-agent review record required.")
        return row["render_job_id"],sha

    def record_private_upload(self, series_id: str, episode_number: int,
                              *, video_id: str, render_job_id: str,
                              master_sha256: str) -> dict[str, Any]:
        """Owner confirms that external upload already happened, not a YouTube API call."""
        _target(series_id,episode_number)
        _video(video_id)
        if (not isinstance(render_job_id,str) or
                not re.fullmatch(r"[0-9a-f]{32}",render_job_id)
                or not isinstance(master_sha256,str)
                or not DIGEST.fullmatch(master_sha256)):
            raise PreviewReviewError("Exact job and video digest required.")
        with self.queue._connection(write=True) as db:
            expected_job,expected_sha=self._current_render(db,series_id,episode_number)
            if (render_job_id,master_sha256)!=(expected_job,expected_sha):
                raise PreviewReviewError("YouTube upload is not bound to current approved master.")
            existing=db.execute("""SELECT video_id,state FROM studio_private_previews
                WHERE series_id=? AND ordinal=? ORDER BY version DESC LIMIT 1""",
                (series_id,episode_number)).fetchone()
            if existing and existing["state"]!="REVISION_REQUESTED":
                raise PreviewReviewError("Existing private preview must be reviewed first.")
            if existing and existing["state"]=="REVISION_REQUESTED":
                previous=db.execute("""SELECT render_job_id,master_sha256
                    FROM studio_private_previews WHERE video_id=?""",
                    (existing["video_id"],)).fetchone()
                if (previous["render_job_id"],previous["master_sha256"])==(
                        render_job_id,master_sha256):
                    raise PreviewReviewError("Requested revision needs a newly approved master render.")
            if existing and existing["video_id"]==video_id:
                raise PreviewReviewError("Every revision needs a different upload/video ID.")
            version=db.execute("""SELECT COALESCE(MAX(version),0)+1 FROM
                studio_private_previews WHERE series_id=? AND ordinal=?""",
                (series_id,episode_number)).fetchone()[0]
            try:
                db.execute("""INSERT INTO studio_private_previews(
                    video_id,series_id,ordinal,render_job_id,master_sha256,
                    state,version,claimed_visibility,platform_privacy_verified,
                    recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (video_id,series_id,episode_number,render_job_id,master_sha256,
                     "PRIVATE_AWAITING_OWNER_REVIEW",version,"PRIVATE",0,time.time()))
            except sqlite3.IntegrityError as exc:
                raise PreviewReviewError("Video ID already registered elsewhere.") from exc
        return {"status":"PRIVATE_PREVIEW_RECORDED_NOT_PLATFORM_VERIFIED",
                "video_id":video_id,"version":version,
                "state":"PRIVATE_AWAITING_OWNER_REVIEW",
                "platform_privacy_verified":False,
                "public_release_authorized":False,
                "upload_performed_by_this_code":False}

    def record_verified_upload(self, report_file: str, expected_report_sha256: str) -> dict:
        """Import owner-transferred M25 PRIVATE API result, pinned to bytes.

        This verifies the report FORMAT and current Pi render lineage; it
        cannot cryptographically attest that the untrusted file truly came
        from Google's OAuth response. Never treats this as PUBLIC consent.
        """
        import hashlib
        from pathlib import Path
        from .episode_assembly import _ensure_private
        p=Path(report_file).expanduser()
        if (not p.is_absolute() or p.is_symlink() or p.suffix.lower()!=".json"
            or not isinstance(expected_report_sha256,str)
            or not DIGEST.fullmatch(expected_report_sha256)):
            raise PreviewReviewError("Private absolute owner-pinned API report required.")
        p=p.resolve()
        _ensure_private(p.parent)
        if not p.is_file() or not 0<p.stat().st_size<=12000:
            raise PreviewReviewError("Missing/oversized M25 private status report.")
        data=p.read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected_report_sha256:
            raise PreviewReviewError("Owner-pinned YouTube report bytes changed.")
        try:r=json.loads(data)
        except (ValueError,TypeError) as exc:
            raise PreviewReviewError("Malformed owner-transferred API report.") from exc
        required={"schema_version","status","series_id","episode_number",
                  "render_job_id","video_sha256","video_id","channel_id",
                  "youtube_privacy","processing_status",
                  "platform_privacy_verified","ready_for_owner_review",
                  "public_release_authorized"}
        if (not isinstance(r,dict) or set(r)!=required
            or type(r["schema_version"]) is not int or r["schema_version"]!=1
            or r["status"]!="YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING"
            or r["youtube_privacy"]!="private"
            or r["processing_status"]!="succeeded"
            or r["platform_privacy_verified"] is not True
            or r["ready_for_owner_review"] is not True
            or r["public_release_authorized"] is not False
            or not isinstance(r["channel_id"],str)
            or not re.fullmatch(r"UC[A-Za-z0-9_-]{22}",r["channel_id"])):
            raise PreviewReviewError("Current processed PRIVATE YouTube status required.")
        recorded=self.record_private_upload(
            r["series_id"],r["episode_number"],
            video_id=r["video_id"],render_job_id=r["render_job_id"],
            master_sha256=r["video_sha256"])
        with self.queue._connection(write=True) as db:
            db.execute("""UPDATE studio_private_previews SET
                platform_privacy_verified=1 WHERE video_id=? AND
                render_job_id=? AND master_sha256=?""",
                (r["video_id"],r["render_job_id"],r["video_sha256"]))
        return {**recorded,"status":"PRIVATE_UPLOAD_API_REPORT_IMPORTED_AWAITING_OWNER",
                "platform_privacy_verified":True,
                "youtube_visibility_currently_guaranteed":False}

    @staticmethod
    def _active(db: sqlite3.Connection, video_id: str) -> sqlite3.Row:
        row=db.execute("SELECT * FROM studio_private_previews WHERE video_id=?",
                       (video_id,)).fetchone()
        if not row or row["state"]!="PRIVATE_AWAITING_OWNER_REVIEW":
            raise PreviewReviewError("Video is not currently awaiting owner review.")
        latest=db.execute("""SELECT video_id FROM studio_private_previews
            WHERE series_id=? AND ordinal=? ORDER BY version DESC LIMIT 1""",
            (row["series_id"],row["ordinal"])).fetchone()
        if not latest or latest["video_id"]!=video_id:
            raise PreviewReviewError("Review belongs to a superseded video.")
        return row

    def add_comment(self, video_id: str, *, text: str,
                    category: str = "other", second: int | None = None) -> dict:
        _video(video_id)
        text=_note(text,required=True)
        if category not in CATEGORIES or (second is not None and (
                type(second) is not int or not 0 <= second <= 3600)):
            raise PreviewReviewError("Category or timecode invalid.")
        with self.queue._connection(write=True) as db:
            row=self._active(db,video_id)
            job,sha=self._current_render(db,row["series_id"],row["ordinal"])
            if (row["render_job_id"],row["master_sha256"])!=(job,sha):
                raise PreviewReviewError("Video master changed; cannot comment on stale preview.")
            db.execute("""INSERT INTO studio_private_preview_feedback
                (video_id,category,second,note,kind,decision,agent_action,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (video_id,category,second,text,"COMMENT",None,"NONE",time.time()))
        return {"status":"OWNER_COMMENT_SAVED","video_id":video_id,
                "public_release_authorized":False}

    def decide(self, video_id: str, decision: str, *,
               note: str = "") -> dict:
        """One immutable decision; approval never calls YouTube/public API."""
        _video(video_id)
        if decision not in DECISIONS:
            raise PreviewReviewError("Unsupported owner review choice.")
        note=_note(note,required=(decision!="APPROVE"))
        with self.queue._connection(write=True) as db:
            row=self._active(db,video_id)
            job,sha=self._current_render(db,row["series_id"],row["ordinal"])
            if (row["render_job_id"],row["master_sha256"])!=(job,sha):
                raise PreviewReviewError("Master changed after private upload; review new version.")
            comment_count=db.execute("""SELECT COUNT(*) FROM
                studio_private_preview_feedback WHERE video_id=?
                AND kind='COMMENT'""",(video_id,)).fetchone()[0]
            if decision=="APPROVE_WITH_NOTES":
                final_state="APPROVED_WITH_NOTES"
                action="CONSIDER_NEXT_EPISODE"
            elif decision=="REQUEST_CHANGES":
                final_state="REVISION_REQUESTED"
                action="TRIAGE_REVISION"
            else:
                final_state="APPROVED"
                action=("CONSIDER_NEXT_EPISODE" if comment_count else "NONE")
            now=time.time()
            db.execute("""INSERT INTO studio_private_preview_feedback
                (video_id,category,second,note,kind,decision,agent_action,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (video_id,"other",None,note,"DECISION",decision,action,now))
            db.execute("""UPDATE studio_private_previews SET state=?,
                reviewed_at=? WHERE video_id=? AND state='PRIVATE_AWAITING_OWNER_REVIEW'""",
                (final_state,now,video_id))
            if action!="NONE":
                db.execute("""UPDATE studio_private_preview_feedback
                    SET agent_action=? WHERE video_id=? AND kind='COMMENT'""",
                    (action,video_id))
            # Revision notes and approved-with-notes become durable triage
            # context for an agent; never auto-queue a new render or upload.
            if action!="NONE":
                db.execute("""INSERT INTO studio_series_notes
                    (series_id,ordinal,note,created_at) VALUES (?,?,?,?)""",
                    (row["series_id"],row["ordinal"],
                     "PRIVATE_PREVIEW_"+action+": "+note,now))
        return {"status":final_state,"video_id":video_id,
                "agent_action":action,
                "recorded_private_upload_only":True,
                "public_release_authorized":False,
                "youtube_visibility_changed":False}

    def candidates(self) -> list[dict]:
        """Only currently approved local master identities; no source paths."""
        with self.queue._connection() as db:
            records=db.execute("""SELECT series_id,ordinal,title FROM
                studio_episodes WHERE state='EPISODE_APPROVED'
                ORDER BY series_id,ordinal LIMIT 120""").fetchall()
            ready=[]
            for row in records:
                try:
                    job,sha=self._current_render(db,row["series_id"],row["ordinal"])
                except PreviewReviewError:
                    continue
                latest=db.execute("""SELECT state FROM studio_private_previews
                    WHERE series_id=? AND ordinal=?
                    ORDER BY version DESC LIMIT 1""",
                    (row["series_id"],row["ordinal"])).fetchone()
                if latest and latest["state"]!="REVISION_REQUESTED":
                    continue
                ready.append({
                    "series_id":row["series_id"],
                    "episode_number":row["ordinal"],
                    "title":row["title"],
                    "render_job_id":job,
                    "master_sha256":sha,
                    "recording_allowed":True,
                })
        return ready

    def snapshot(self, *, limit: int = 50) -> dict[str, Any]:
        if type(limit) is not int or not 1<=limit<=100:
            raise PreviewReviewError("Invalid review query bound.")
        with self.queue._connection() as db:
            rows=db.execute("""SELECT p.video_id,p.series_id,p.ordinal,
                p.render_job_id,p.master_sha256,p.state,p.version,
                p.claimed_visibility,p.platform_privacy_verified,
                p.recorded_at,p.reviewed_at,e.title
                FROM studio_private_previews p
                JOIN studio_episodes e ON e.series_id=p.series_id
                    AND e.ordinal=p.ordinal
                ORDER BY p.recorded_at DESC,p.video_id LIMIT ?""",
                (limit,)).fetchall()
            items=[]
            for row in rows:
                notes=db.execute("""SELECT category,second,note,kind,
                    decision,agent_action,created_at FROM
                    studio_private_preview_feedback
                    WHERE video_id=? ORDER BY feedback_id""",
                    (row["video_id"],)).fetchall()
                items.append({
                    "video_id":row["video_id"],
                    "url":"https://www.youtube.com/watch?v="+row["video_id"],
                    "series_id":row["series_id"],
                    "episode_number":row["ordinal"],
                    "title":row["title"],
                    "version":row["version"],
                    "state":row["state"],
                    "claimed_visibility":"PRIVATE",
                    "platform_privacy_verified":bool(row["platform_privacy_verified"]),
                    "recorded_at":row["recorded_at"],
                    "reviewed_at":row["reviewed_at"],
                    "comments":[dict(comment) for comment in notes],
                    "release_authorized":False,
                })
        return {
            "status":"OWNER_PRIVATE_PREVIEW_TRACKING_ONLY",
            "previews":items,
            "pending_review":sum(1 for x in items if x["state"]=="PRIVATE_AWAITING_OWNER_REVIEW"),
            "revision_requests":sum(1 for x in items if x["state"]=="REVISION_REQUESTED"),
            "youtube_api_connected":False,
            "public_release_authorized":False,
        }
