"""M63: recovered YouTube PRIVATE owner decisions, separate M24 lineage.

Uses the existing M24 note categories, timestamp/decision vocabulary and
review UI, but never forges a completed ordinary Pi render or changes the
old BLOCKED episode. Decisions never send any YouTube visibility API call.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .private_preview_review import (
    CATEGORIES,DECISIONS,_note,_video,PreviewReviewError
)
from .recovery_final_qa import RecoveryFinalQA,RecoveryQualityError
from .recovery_private_upload_gate import VERIFIED
from .studio_queue import StudioQueue

class RecoveryOwnerReviewError(PreviewReviewError):
    pass


class RecoveryOwnerReview:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def has_video(self,video_id:str)->bool:
        _video(video_id)
        with self.queue._connection() as db:
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE
                name='studio_recovery_uploads' AND type='table'""").fetchone():
                return False
            return bool(db.execute("""SELECT 1 FROM studio_recovery_uploads
                WHERE video_id=?""",(video_id,)).fetchone())

    def _current(self,db:sqlite3.Connection,video_id:str)->sqlite3.Row:
        _video(video_id)
        row=db.execute("""SELECT u.*,i.series_id,i.ordinal,e.title
            FROM studio_recovery_uploads u
            JOIN studio_recovery_intents i ON i.proposal_id=u.proposal_id
            JOIN studio_episodes e ON e.series_id=i.series_id AND e.ordinal=i.ordinal
            WHERE u.video_id=?""",(video_id,)).fetchone()
        if not row or row["state"]!=VERIFIED:
            raise RecoveryOwnerReviewError("M63 authenticated PRIVATE preview unavailable.")
        if db.execute("""SELECT 1 FROM studio_recovery_owner_decisions
                    WHERE proposal_id=?""",(row["proposal_id"],)).fetchone():
            raise RecoveryOwnerReviewError("Owner already decided this recovery version.")
        try:
            lease,pins=RecoveryFinalQA(self.queue)._source(db,row["proposal_id"])
        except (RecoveryQualityError,ValueError,OSError) as exc:
            raise RecoveryOwnerReviewError("Recovered media lineage no longer current.") from exc
        if (lease["reserved_job_id"]!=row["recovery_job_id"] or
            lease["result_sha256"]!=row["master_sha256"]):
            raise RecoveryOwnerReviewError("M63 owner review master has changed.")
        return row

    def add_comment(self,video_id:str,*,text:str,category:str="other",
                    second:int|None=None)->dict:
        content=_note(text,required=True)
        if category not in CATEGORIES or (second is not None and
            (type(second) is not int or not 0<=second<=3600)):
            raise RecoveryOwnerReviewError("Invalid timestamped review category.")
        with self.queue._connection(write=True) as db:
            row=self._current(db,video_id)
            db.execute("""INSERT INTO studio_recovery_owner_feedback
                (proposal_id,category,second,note,kind,decision,created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (row["proposal_id"],category,second,content,"COMMENT",None,
                 self.queue.clock()))
        return {"status":"OWNER_COMMENT_SAVED","video_id":video_id,
                "public_release_authorized":False}

    def decide(self,video_id:str,decision:str,*,note:str="")->dict:
        if decision not in DECISIONS:
            raise RecoveryOwnerReviewError("Invalid private review decision.")
        message=_note(note,required=decision!="APPROVE")
        status={"APPROVE":"APPROVED",
                "APPROVE_WITH_NOTES":"APPROVED_WITH_NOTES",
                "REQUEST_CHANGES":"REVISION_REQUESTED"}[decision]
        action=("TRIAGE_REVISION" if decision=="REQUEST_CHANGES" else
                "CONSIDER_NEXT_EPISODE" if decision=="APPROVE_WITH_NOTES"
                else "NONE")
        with self.queue._connection(write=True) as db:
            row=self._current(db,video_id)
            now=self.queue.clock()
            db.execute("""INSERT INTO studio_recovery_owner_decisions
                VALUES(?,?,?,?,?)""",(row["proposal_id"],video_id,
                                       status,message,now))
            db.execute("""INSERT INTO studio_recovery_owner_feedback
                (proposal_id,category,second,note,kind,decision,created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (row["proposal_id"],"other",None,message,"DECISION",decision,now))
            if action!="NONE":
                db.execute("""INSERT INTO studio_series_notes
                    (series_id,ordinal,note,created_at)
                    VALUES(?,?,?,?)""",
                    (row["series_id"],row["ordinal"],
                     "RECOVERY_PRIVATE_"+action+": "+message,now))
        return {"status":status,"video_id":video_id,
                "agent_action":action,
                "youtube_visibility_changed":False,
                "public_release_authorized":False}

    def snapshot(self,*,limit:int=50)->dict[str,Any]:
        if type(limit) is not int or not 1<=limit<=100:
            raise RecoveryOwnerReviewError("Bounded owner review limit required.")
        with self.queue._connection() as db:
            exists=db.execute("""SELECT 1 FROM sqlite_master WHERE
                name='studio_recovery_uploads' AND type='table'""").fetchone()
            if not exists:
                return {"previews":[],"pending_review":0,
                        "revision_requests":0,
                        "public_release_authorized":False}
            rows=db.execute("""SELECT u.proposal_id,u.video_id,u.recovery_job_id,
                u.master_sha256,u.state AS upload_state,u.created_at,
                i.series_id,i.ordinal,e.title,
                d.state AS decision_state,d.reviewed_at
                FROM studio_recovery_uploads u
                JOIN studio_recovery_intents i ON i.proposal_id=u.proposal_id
                JOIN studio_episodes e ON e.series_id=i.series_id
                    AND e.ordinal=i.ordinal
                LEFT JOIN studio_recovery_owner_decisions d
                    ON d.proposal_id=u.proposal_id
                WHERE u.state=?
                ORDER BY u.updated_at DESC LIMIT ?""",(VERIFIED,limit)).fetchall()
            previews=[]
            for row in rows:
                notes=[dict(n) for n in db.execute("""SELECT category,second,
                    note,kind,decision,created_at
                    FROM studio_recovery_owner_feedback WHERE proposal_id=?
                    ORDER BY feedback_id""",(row["proposal_id"],)).fetchall()]
                previews.append({
                    "video_id":row["video_id"],
                    "url":"https://www.youtube.com/watch?v="+row["video_id"],
                    "series_id":row["series_id"],
                    "episode_number":row["ordinal"],
                    "title":row["title"],
                    "version":1,
                    "state":row["decision_state"] or "PRIVATE_AWAITING_OWNER_REVIEW",
                    "claimed_visibility":"PRIVATE",
                    "platform_privacy_verified":True,
                    "recorded_at":row["created_at"],
                    "reviewed_at":row["reviewed_at"],
                    "comments":notes,
                    "recovery":True,
                    "release_authorized":False,
                })
        return {"status":"RECOVERY_OWNER_PRIVATE_REVIEW_LOCAL_ONLY",
                "previews":previews,
                "pending_review":sum(x["state"]=="PRIVATE_AWAITING_OWNER_REVIEW"
                                     for x in previews),
                "revision_requests":sum(x["state"]=="REVISION_REQUESTED"
                                         for x in previews),
                "youtube_api_connected":False,
                "public_release_authorized":False}
