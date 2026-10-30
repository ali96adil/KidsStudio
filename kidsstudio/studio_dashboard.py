"""Read-only, loopback-only KidsStudio production dashboard.

Uses Studio Brain's existing database and SeriesManager. No second database,
no actions to execute models, no publishing, no editing or provider secrets.
The dashboard is an observer; status is always derived from durable records.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import sqlite3
from pathlib import Path
import sys
from urllib.parse import urlsplit

from .series_manager import SeriesManager
from .acceptance_review import inspect_studio, AcceptanceError
from .studio_queue import StudioQueue


STATE_COPY = {
    "PLANNED": ("بانتظار السيناريو", "planned"),
    "DRAFT_QUEUED": ("السيناريو قيد التحضير", "working"),
    "REVIEW_QUEUED": ("السيناريو قيد المراجعة", "working"),
    "OWNER_SCRIPT_REVIEW": ("بانتظار اعتماد السيناريو", "review"),
    "SCRIPT_APPROVED": ("السيناريو معتمد، ينتظر الإنتاج", "ready"),
    "RENDER_QUEUED": ("مهمة الإنتاج في الطابور", "working"),
    "RENDERED_QA_PENDING": ("الفيديو مُنتج، ينتظر فحص الجودة", "review"),
    "EPISODE_APPROVED": ("الحلقة معتمدة داخلياً", "complete"),
    "BLOCKED": ("متوقفة وتحتاج تدخلاً", "blocked"),
}
STAGES = [
    ("curriculum", "المنهج"),
    ("script", "السيناريو"),
    ("editorial", "المراجعة التحريرية"),
    ("voice", "الصوت"),
    ("animation", "التحريك"),
    ("face", "تحسين الوجه"),
    ("assembly", "المونتاج"),
    ("final_qa", "الفحص النهائي"),
]


def stage_timeline(state: str, *, render_kind: str | None = None,
                   stage_progress: dict[str, str] | None = None) -> list[dict[str, str]]:
    """Conservative timeline: do not invent separate voice/LTX completion.

    The current versioned Studio Brain queue does not have distinct voice,
    A2V or face worker receipts. Even a finished composite video cannot prove
    a specific TTS, LTX, or face job actually ran.
    """
    if state not in STATE_COPY:
        state = "BLOCKED"
    script_started = state != "PLANNED"
    script_ready = state in {"OWNER_SCRIPT_REVIEW", "SCRIPT_APPROVED",
                             "RENDER_QUEUED", "RENDERED_QA_PENDING", "EPISODE_APPROVED"}
    script_approved = state in {"SCRIPT_APPROVED", "RENDER_QUEUED",
                                "RENDERED_QA_PENDING", "EPISODE_APPROVED"}
    rendered = state in {"RENDERED_QA_PENDING", "EPISODE_APPROVED"}
    owner_ok = state == "EPISODE_APPROVED"
    # A composite MP4 never proves independent TTS/LTX/face quality.
    # A voice or animation stage only becomes complete after owner QA.
    stage_progress = stage_progress or {}
    def tracked(kind: str) -> str:
        status = stage_progress.get(kind)
        return {"QA_APPROVED":"complete","PENDING_QA":"in_review",
                "QUEUED":"working","BLOCKED":"blocked",
                "RESET_FOR_RETRY":"pending"}.get(status,"not_tracked")
    return [
        {"id":"curriculum","name":STAGES[0][1],"status":"complete"},
        {"id":"script","name":STAGES[1][1],
         "status":"complete" if script_approved else
                  ("in_review" if script_ready else "working" if script_started else "pending")},
        {"id":"editorial","name":STAGES[2][1],
         "status":"complete" if script_approved else
                  ("in_review" if script_ready else "pending")},
        {"id":"voice","name":STAGES[3][1],
         "status":tracked("voice_synthesize")},
        {"id":"animation","name":STAGES[4][1],
         "status":tracked("ltx_animate")},
        {"id":"face","name":STAGES[5][1],"status":"not_tracked"},
        {"id":"assembly","name":STAGES[6][1],
         "status":"complete" if rendered else
                  ("working" if state=="RENDER_QUEUED" else "pending")},
        {"id":"final_qa","name":STAGES[7][1],
         "status":"complete" if owner_ok else
                  ("in_review" if state=="RENDERED_QA_PENDING" else "pending")},
    ]


def build_snapshot(queue: StudioQueue) -> dict:
    registry = SeriesManager(queue)
    data = registry.snapshot()
    status=queue.status()
    # Explicitly do not return raw queue payloads, full job result records,
    # source paths, API prompts, original scripts, or provider credentials.
    ids={ep["render_job_id"] for ep in data["episodes"] if ep["render_job_id"]}
    render_kinds={}
    stage_states={}
    quality_states={}
    audio_states={}
    scene_states={}
    scene_ai_states={}
    scene_visual_states={}
    orchestration_states={}
    recovery_states={}
    recovery_summary={"state":"NOT_CONFIGURED","reserved":0,
                      "ready":0,"leased":0,"waiting_final_review":0,
                      "blocked":0,"awaiting_ai":0,
                      "ai_private_ready":0,"needs_fix":0,
                      "private_handoff":0,
                      "private_upload_ready":0,"private_uploading":0,
                      "private_processing":0,"private_owner_review":0,
                      "private_approved":0,"private_revisions":0,
                      "public_release_authorized":False}
    preview_states={}
    preview_summary={"state":"NOT_CONFIGURED","pending_review":0,
                     "revision_requests":0,"approved":0,"approved_with_notes":0}
    learning_summary={"state":"NOT_CONFIGURED","observed_windows":0,
                      "proposed":0,"adopted":0,"recommendations":[]}
    scene_tracking_installed=False
    audio_tracking_installed=False
    stage_tracking_installed=False
    with queue._connection() as db:
        has_previews=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_private_previews'""").fetchone())
        if has_previews:
            preview_summary["state"]="OWNER_LOCAL_REVIEW_NOT_YOUTUBE_CONNECTED"
            for item in db.execute("""SELECT video_id,series_id,ordinal,state,
                version,platform_privacy_verified
                FROM studio_private_previews ORDER BY version DESC"""):
                key=(item["series_id"],item["ordinal"])
                if key not in preview_states:
                    preview_states[key]={
                        "video_id":item["video_id"],"state":item["state"],
                        "version":item["version"],
                        "url":"https://www.youtube.com/watch?v="+item["video_id"],
                        "youtube_visibility_verified":bool(item["platform_privacy_verified"]),
                        "youtube_visibility_currently_guaranteed":False,
                    }
                    field={"PRIVATE_AWAITING_OWNER_REVIEW":"pending_review",
                           "REVISION_REQUESTED":"revision_requests",
                           "APPROVED":"approved",
                           "APPROVED_WITH_NOTES":"approved_with_notes"}.get(item["state"])
                    if field: preview_summary[field]+=1
        has_learning=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_learning_proposals'""").fetchone())
        if has_learning:
            learning_summary["state"]="OWNER_REVIEWED_ANALYTICS_ONLY"
            learning_summary["observed_windows"]=db.execute(
                "SELECT COUNT(*) FROM studio_video_metrics").fetchone()[0]
            for record in db.execute("""SELECT status,COUNT(*) AS n
                FROM studio_learning_proposals GROUP BY status"""):
                if record["status"]=="PROPOSED":
                    learning_summary["proposed"]=record["n"]
                if record["status"]=="ADOPT_FOR_FUTURE_EXPERIMENT":
                    learning_summary["adopted"]=record["n"]
            for record in db.execute("""SELECT series_id,feature_name,
                winning_style,comparison_style,status FROM studio_learning_proposals
                ORDER BY created_at DESC LIMIT 8"""):
                learning_summary["recommendations"].append({
                    "series_id":record["series_id"],
                    "feature":record["feature_name"],
                    "candidate":record["winning_style"],
                    "baseline":record["comparison_style"],
                    "state":record["status"]
                })
        recovery_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_recovery_reservations'""").fetchone())
        recovery_leases_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_recovery_leases'""").fetchone())
        if recovery_installed:
            recovery_summary["state"]="PRIVATE_RECOVERY_METADATA_ONLY"
            if recovery_leases_installed:
                records=db.execute("""SELECT i.series_id,i.ordinal,
                    r.state AS reservation_state,l.state AS lease_state
                    FROM studio_recovery_reservations r
                    JOIN studio_recovery_intents i ON i.proposal_id=r.proposal_id
                    LEFT JOIN studio_recovery_leases l
                      ON l.proposal_id=r.proposal_id
                    ORDER BY r.created_at DESC""")
            else:
                records=db.execute("""SELECT i.series_id,i.ordinal,
                    r.state AS reservation_state,NULL AS lease_state
                    FROM studio_recovery_reservations r
                    JOIN studio_recovery_intents i ON i.proposal_id=r.proposal_id
                    ORDER BY r.created_at DESC""")
            for r in records:
                state=r["lease_state"] or r["reservation_state"]
                bucket={
                    "M60_RECOVERY_JOB_RESERVED_NOT_DISPATCHABLE":"reserved",
                    "M61_READY_PRIVATE_RECOVERY":"ready",
                    "M61_LEASED_PRIVATE_RECOVERY":"leased",
                    "M61_RENDERED_PENDING_FINAL_M7_OWNER_REVIEW":"waiting_final_review",
                    "M61_FAILED_REQUIRES_MANUAL_RECONCILIATION":"blocked",
                }.get(state)
                if bucket:
                    recovery_summary[bucket]+=1
                key=(r["series_id"],r["ordinal"])
                if key not in recovery_states:
                    recovery_states[key]={
                        "state":state,
                        "hardware_qualified":False,
                        "automatically_public":False,
                        "owner_private_review_required":True}
        recovery_qa_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_recovery_final_qa'""").fetchone())
        if recovery_qa_installed:
            handoff_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='studio_recovery_private_handoffs'""").fetchone())
            recovery_summary["state"]="PRIVATE_AI_QA_HANDOFF_NO_UPLOAD"
            sql=("""SELECT i.series_id,i.ordinal,q.state AS qa_state,
                h.state AS handoff_state
                FROM studio_recovery_final_qa q
                JOIN studio_recovery_intents i ON i.proposal_id=q.proposal_id
                LEFT JOIN studio_recovery_private_handoffs h
                  ON h.proposal_id=q.proposal_id
                ORDER BY q.updated_at DESC"""
                if handoff_installed else
                """SELECT i.series_id,i.ordinal,q.state AS qa_state,
                    NULL AS handoff_state
                    FROM studio_recovery_final_qa q
                    JOIN studio_recovery_intents i ON i.proposal_id=q.proposal_id
                    ORDER BY q.updated_at DESC""")
            for result in db.execute(sql):
                stage=result["handoff_state"] or result["qa_state"]
                bucket={
                    "M62_TECH_PASSED_AWAITING_INDEPENDENT_AI":"awaiting_ai",
                    "M62_AI_INTERNAL_READY_PRIVATE_ONLY_NOT_UPLOADED":"ai_private_ready",
                    "M62_AI_INTERNAL_CHANGES_REQUIRED":"needs_fix",
                    "M62_PRIVATE_UPLOAD_HANDOFF_STAGED_NOT_QUEUED":"private_handoff",
                }.get(stage)
                if bucket:recovery_summary[bucket]+=1
                key=(result["series_id"],result["ordinal"])
                if key in recovery_states:
                    old=recovery_states[key]["state"]
                    if (old=="M61_RENDERED_PENDING_FINAL_M7_OWNER_REVIEW"
                        and recovery_summary["waiting_final_review"]>0):
                        recovery_summary["waiting_final_review"]-=1
                    recovery_states[key]["state"]=stage
                    recovery_states[key]["automatic_youtube_upload"]=False
                    recovery_states[key]["owner_private_review_required"]=True
        m63_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_recovery_uploads'""").fetchone())
        if m63_installed:
            decisions_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='studio_recovery_owner_decisions'""").fetchone())
            recovery_summary["state"]="M63_PRIVATE_UPLOAD_AND_OWNER_REVIEW"
            query=("""SELECT i.series_id,i.ordinal,u.state upload_state,
                    d.state decision_state FROM studio_recovery_uploads u
                    JOIN studio_recovery_intents i ON i.proposal_id=u.proposal_id
                    LEFT JOIN studio_recovery_owner_decisions d
                      ON d.proposal_id=u.proposal_id
                    ORDER BY u.updated_at DESC"""
                    if decisions_installed else
                    """SELECT i.series_id,i.ordinal,u.state upload_state,
                    NULL decision_state FROM studio_recovery_uploads u
                    JOIN studio_recovery_intents i ON i.proposal_id=u.proposal_id
                    ORDER BY u.updated_at DESC""")
            for row in db.execute(query):
                stage=row["decision_state"] or row["upload_state"]
                key=(row["series_id"],row["ordinal"])
                field={
                    "M63_PRIVATE_UPLOAD_READY_ONE_SHOT":"private_upload_ready",
                    "M63_PRIVATE_UPLOAD_LEASED":"private_uploading",
                    "M63_YOUTUBE_PRIVATE_PROCESSING_PENDING":"private_processing",
                    "M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING":"private_owner_review",
                    "APPROVED":"private_approved",
                    "APPROVED_WITH_NOTES":"private_approved",
                    "REVISION_REQUESTED":"private_revisions",
                }.get(stage)
                if field:recovery_summary[field]+=1
                # The M62 handoff has become an actual M63 upload state.
                # Do not double-count it as still waiting to be dispatched.
                if (key in recovery_states and
                    recovery_states[key]["state"]==
                        "M62_PRIVATE_UPLOAD_HANDOFF_STAGED_NOT_QUEUED" and
                    recovery_summary["private_handoff"]>0):
                    recovery_summary["private_handoff"]-=1
                if key in recovery_states:
                    recovery_states[key]["state"]=stage
                    recovery_states[key]["automatic_youtube_upload"]=False
                    recovery_states[key]["youtube_visibility_currently_guaranteed"]=False
                    recovery_states[key]["owner_private_review_required"]=True
        orchestration_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_orchestrator_plans'""").fetchone())
        if orchestration_installed:
            for pinned in db.execute("""SELECT o.series_id,o.ordinal,
                o.script_sha256,e.source_sha256 AS current_source_sha256
                FROM studio_orchestrator_plans o
                LEFT JOIN studio_episodes e ON e.series_id=o.series_id
                    AND e.ordinal=o.ordinal"""):
                orchestration_states[(pinned["series_id"],pinned["ordinal"])]={
                    "state":("PINNED_SOURCE_CURRENT_FILE_NOT_RECHECKED" if
                        pinned["script_sha256"]==pinned["current_source_sha256"]
                        else "BLOCKED_SCRIPT_CHANGED"),
                    "hardware_qualification_ready":False,
                    "private_upload_authorized":False
                }
        scene_tracking_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_scenes'""").fetchone())
        if scene_tracking_installed:
            for item in db.execute("""SELECT series_id,ordinal,COUNT(*) AS total
                FROM studio_scenes GROUP BY series_id,ordinal"""):
                scene_states[(item["series_id"],item["ordinal"])]={
                    "total":item["total"],"voice_approved":0,
                    "ltx_approved":0,"blocked":0}
            for item in db.execute("""SELECT series_id,ordinal,stage,state
                FROM studio_scene_stages"""):
                state=scene_states.get((item["series_id"],item["ordinal"]))
                if state is None:
                    continue
                if item["state"]=="QA_APPROVED":
                    if item["stage"]=="voice_synthesize":
                        state["voice_approved"]+=1
                    if item["stage"]=="ltx_animate":
                        state["ltx_approved"]+=1
                if item["state"]=="BLOCKED":
                    state["blocked"]+=1
        ai_scene_tracking_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_scene_ai_reviews'""").fetchone())
        if ai_scene_tracking_installed:
            for item in db.execute("""SELECT a.series_id,a.ordinal,
                    a.stage,a.state FROM studio_scene_ai_reviews a
                JOIN studio_scene_stages s
                    ON s.series_id=a.series_id AND s.ordinal=a.ordinal
                    AND s.scene=a.scene AND s.stage=a.stage
                    AND s.job_id=a.job_id"""):
                key=(item["series_id"],item["ordinal"])
                ai=scene_ai_states.setdefault(key,{
                    "state":"AI_SCENE_REVIEW_TRACKED_NOT_MODEL_INFERENCE_PROOF",
                    "voice_ready":0,"ltx_ready":0,"needs_fix":0})
                if item["state"]=="AI_SCENE_READY_PRIVATE_ONLY":
                    if item["stage"]=="voice_synthesize":
                        ai["voice_ready"]+=1
                    if item["stage"]=="ltx_animate":
                        ai["ltx_ready"]+=1
                elif item["state"]=="AI_SCENE_NEEDS_FIX":
                    ai["needs_fix"]+=1
        # M36 read-only overview: only the current signed LTX observation
        # survives, never claim that sampled silent frames prove lip sync.
        has_m36=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_scene_visual_observations'""").fetchone())
        if has_m36:
            # An M37 real synchronized AV review supersedes the earlier
            # M36 frame-only uncertainty for the SAME job. Do not show
            # "AV model missing" once a current M28 verdict exists.
            reviewed_filter=(""" AND NOT EXISTS (
                SELECT 1 FROM studio_scene_ai_reviews a
                WHERE a.series_id=v.series_id AND a.ordinal=v.ordinal
                AND a.scene=v.scene AND a.stage='ltx_animate'
                AND a.job_id=v.ltx_job_id)""" if ai_scene_tracking_installed
                else "")
            query="""SELECT v.series_id,v.ordinal,COUNT(*) AS n
                FROM studio_scene_visual_observations v
                JOIN studio_scene_stages st ON st.series_id=v.series_id
                AND st.ordinal=v.ordinal AND st.scene=v.scene
                AND st.stage='ltx_animate' AND st.job_id=v.ltx_job_id
                WHERE st.state='PENDING_QA'
                AND v.state='AV_AUDIO_REVIEW_REQUIRED'"""+reviewed_filter+"""
                GROUP BY v.series_id,v.ordinal"""
            for item in db.execute(query):
                scene_visual_states[(item["series_id"],item["ordinal"])]={
                    "state":"M36_AV_AUDIO_REVIEW_REQUIRED",
                    "scenes_waiting_audio_video":item["n"],
                    "lip_sync_verified":False,
                    "public_release_authorized":False}
        repairs_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_scene_repair_attempts'""").fetchone())
        if repairs_installed:
            for item in db.execute("""SELECT r.series_id,r.ordinal,
                COUNT(*) AS total,
                SUM(CASE WHEN s.job_id=r.new_job_id AND
                    s.state IN ('QUEUED','PENDING_QA') THEN 1 ELSE 0 END)
                    AS active
                FROM studio_scene_repair_attempts r
                JOIN studio_scene_stages s ON s.series_id=r.series_id
                    AND s.ordinal=r.ordinal AND s.scene=r.scene
                    AND s.stage=r.stage
                GROUP BY r.series_id,r.ordinal"""):
                key=(item["series_id"],item["ordinal"])
                scenes=scene_states.setdefault(key,{"total":0,
                    "voice_approved":0,"ltx_approved":0,"blocked":0})
                scenes["repairs_queued_total"]=item["total"]
                scenes["repairs_current_pending"]=item["active"]
        audio_tracking_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_audio_checks'""").fetchone())
        if audio_tracking_installed:
            for row in db.execute("""SELECT a.series_id,a.ordinal,a.status,
                a.correlation
                FROM studio_audio_checks a
                JOIN studio_episode_stages s
                ON s.series_id=a.series_id AND s.ordinal=a.ordinal
                  AND s.stage='ltx_animate' AND s.job_id=a.ltx_job_id"""):
                audio_states[(row["series_id"],row["ordinal"])]={
                    "state":row["status"],"correlation":row["correlation"]
                }
        stage_tracking_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_episode_stages'""").fetchone())
        if stage_tracking_installed:
            for stage in db.execute("""SELECT series_id,ordinal,stage,state
                FROM studio_episode_stages"""):
                stage_states.setdefault((stage["series_id"],stage["ordinal"]),{})[stage["stage"]]=stage["state"]
    with queue._connection() as db:
        quality_installed=bool(db.execute("""SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='studio_quality_reviews'""").fetchone())
        if quality_installed:
            for row in db.execute("""SELECT q.series_id,q.ordinal,q.render_job_id,
                q.state,q.checks_passed
                FROM studio_quality_reviews q
                JOIN studio_episodes e ON
                e.series_id=q.series_id AND e.ordinal=q.ordinal
                AND e.render_job_id=q.render_job_id"""):
                quality_states[(row["series_id"],row["ordinal"])]={
                    "state":row["state"],"criteria_passed":row["checks_passed"],
                    "internal_review_mode":("TWO_INDEPENDENT_AI_PRIVATE_ONLY"
                        if row["state"]=="AI_INTERNAL_READY_PRIVATE_ONLY"
                        else "OWNER_OR_LEGACY"),
                }
    if ids:
        with queue._connection() as db:
            for identifier in ids:
                row=db.execute("SELECT kind FROM jobs WHERE job_id=?",(identifier,)).fetchone()
                if row:
                    render_kinds[identifier]=row["kind"]
    counts={"episodes_total":len(data["episodes"]),
            "scripts_waiting_production":0,
            "episodes_waiting_qa":0,"episodes_approved":0,
            "episodes_blocked":0,"open_jobs":0}
    counts["open_jobs"]=status["counts"]["QUEUED"] + status["counts"]["LEASED"]
    episodes=[]
    for ep in data["episodes"]:
        state=ep["state"]
        label,tone=STATE_COPY.get(state,("حالة غير معروفة","blocked"))
        if state=="SCRIPT_APPROVED":
            counts["scripts_waiting_production"]+=1
        if state=="RENDERED_QA_PENDING":
            counts["episodes_waiting_qa"]+=1
        if state=="EPISODE_APPROVED":
            counts["episodes_approved"]+=1
        if state=="BLOCKED":
            counts["episodes_blocked"]+=1
        episodes.append({
            "series_id":ep["series_id"], "ordinal":ep["ordinal"],
            "title":ep["title"],"objective":ep["objective"],"state":state,
            "private_preview":preview_states.get((ep["series_id"],ep["ordinal"]),{
                "state":"NOT_RECORDED","youtube_visibility_verified":False}),
            "status_label":label,"tone":tone,"revision":ep["revision"],
            "scene_progress":scene_states.get((ep["series_id"],ep["ordinal"]),{
                "total":0,"voice_approved":0,"ltx_approved":0,"blocked":0}),
            "ai_scene_reviews":scene_ai_states.get((ep["series_id"],ep["ordinal"]),{
                "state":"NOT_STARTED",
                "voice_ready":0,"ltx_ready":0,"needs_fix":0}),
            "visual_av_review":scene_visual_states.get((ep["series_id"],ep["ordinal"]),{
                "state":"NOT_STARTED","scenes_waiting_audio_video":0,
                "lip_sync_verified":False,"public_release_authorized":False}),
            "recovery":recovery_states.get((ep["series_id"],ep["ordinal"]),{
                "state":"NO_RECOVERY_ATTEMPT","automatically_public":False}),
            "orchestrator":orchestration_states.get((ep["series_id"],ep["ordinal"]),{
                "state":"NOT_PINNED",
                "hardware_qualification_ready":False,
                "private_upload_authorized":False}),
            "audio_continuity":audio_states.get((ep["series_id"],ep["ordinal"]),
                  {"state":"NOT_RECORDED" if audio_tracking_installed else "NOT_CONFIGURED",
                   "correlation":None}),
            "quality":quality_states.get((ep["series_id"],ep["ordinal"]),
                  {"state":"NOT_STARTED" if quality_installed else "NOT_CONFIGURED",
                   "criteria_passed":0}),
            "stages":stage_timeline(state,render_kind=render_kinds.get(ep["render_job_id"]),
                                     stage_progress=stage_states.get((ep["series_id"],ep["ordinal"]))),
        })
    series=[{"id":s["series_id"],"title":s["title"],"language":s["language"],
             "state":s["state"],"total":s["total"],
             "approved":s["episodes_approved"]} for s in data["series"]]
    notes=[{"series_id":n["series_id"],"episode":n["ordinal"],
            "text":n["note"],"created_at":n["created_at"]} for n in data["notes"][:50]]
    return {"version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
            "overview":counts,"series":series,"episodes":episodes,"notes":notes,
            "learning":learning_summary,
            "recovery":recovery_summary,
            "private_previews":preview_summary,
            "queue":{"paused":status["paused"],"counts":status["counts"]},
            "limits":{"media_execution":False,"publishing":False,
                      "voice_and_ltx_tracking":("RECEIPT_GATED" if stage_tracking_installed
                                                 else "NOT_YET_CONNECTED"),
                      "audio_continuity_tracking":("CURRENT_LTX_RECEIPT_GATED" if audio_tracking_installed
                                                     else "NOT_CONFIGURED"),
                      "episode_qa_tracking":("EVIDENCE_GATED" if quality_installed
                                             else "NOT_CONFIGURED"),
                      "scene_tracking":("PER_SCENE_QA" if scene_tracking_installed else "NOT_CONFIGURED"),
                      "private_preview_review":preview_summary["state"],
                      "m32_hardware_qualification_ready":False,
                      "m32_software_full_cycle_qualified":False,
                      "data_source":"Studio Brain SQLite; read-only"},
            }


def make_handler(queue: StudioQueue):
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version="KidsStudioDashboard/1.0"
        def log_message(self, fmt, *args):
            # Do not persist private query strings or access addresses.
            pass

        def _reply(self, code, payload, content_type):
            self.send_response(code)
            self.send_header("Content-Type",content_type)
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; "
                             "style-src 'self'; img-src 'self' data:; "
                             "object-src 'none'; base-uri 'none'; "
                             "frame-ancestors 'none'; connect-src 'self'")
            self.send_header("Content-Length",str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            # Reject DNS rebinding via malicious Host header, even though
            # the listener itself is bound to the loopback interface.
            host=(self.headers.get("Host") or "").split(":",1)[0].lower()
            if host not in ("127.0.0.1","localhost","[::1]"):
                self._reply(403,b"Forbidden","text/plain; charset=utf-8")
                return
            path=urlsplit(self.path)
            if path.query or path.fragment:
                self._reply(400,b"Query strings disabled","text/plain; charset=utf-8")
                return
            if path.path in ("/", "/index.html"):
                resource="dashboard.html";mime="text/html; charset=utf-8"
            elif path.path=="/dashboard.js":
                resource="dashboard.js";mime="application/javascript; charset=utf-8"
            elif path.path=="/dashboard.css":
                resource="dashboard.css";mime="text/css; charset=utf-8"
            elif path.path=="/api/overview":
                try:
                    body=json.dumps(build_snapshot(queue),ensure_ascii=False,
                                    separators=(",",":")).encode("utf-8")
                except (OSError,ValueError,RuntimeError):
                    self._reply(503,b'{"error":"snapshot_unavailable"}',
                                "application/json; charset=utf-8")
                    return
                self._reply(200,body,"application/json; charset=utf-8")
                return
            elif path.path=="/api/acceptance":
                # Explicit read-only manual report; no backup generation,
                # external engine execution, media transfers or publishing.
                try:
                    body=json.dumps(inspect_studio(queue),ensure_ascii=False,
                                    separators=(",",":")).encode("utf-8")
                except (AcceptanceError,OSError,ValueError,sqlite3.DatabaseError):
                    self._reply(503,b'{"error":"acceptance_snapshot_unavailable"}',
                                "application/json; charset=utf-8")
                    return
                self._reply(200,body,"application/json; charset=utf-8")
                return
            elif path.path=="/api/health":
                self._reply(200,b'{"status":"ok","read_only":true}',
                            "application/json; charset=utf-8")
                return
            else:
                self._reply(404,b"Not Found","text/plain; charset=utf-8")
                return
            # No arbitrary paths; read three fixed packaged assets only.
            file=Path(__file__).parent/"dashboard_assets"/resource
            if not file.is_file():
                self._reply(503,b"Dashboard assets missing","text/plain; charset=utf-8")
                return
            self._reply(200,file.read_bytes(),mime)

        def do_POST(self):
            self._reply(405,b"Read-only dashboard","text/plain; charset=utf-8")
        do_PUT=do_DELETE=do_PATCH=do_POST

    return DashboardHandler


def serve(db: Path, port: int = 8793) -> None:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Port must be 1024..65535.")
    queue=StudioQueue(db)
    # Fail closed on absent/uninitialized series schema: don't silently create DB.
    SeriesManager(queue).snapshot()
    httpd=ThreadingHTTPServer(("127.0.0.1",port),make_handler(queue))
    print(f"KidsStudio read-only dashboard: http://127.0.0.1:{port}/",flush=True)
    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(prog="studio-dashboard",
        description="Read-only local KidsStudio production board")
    p.add_argument("--db",required=True,type=Path)
    p.add_argument("--port",type=int,default=8793)
    args=p.parse_args(argv)
    try:
        serve(args.db,args.port)
        return 0
    except (ValueError,OSError) as exc:
        print("STUDIO_DASHBOARD_ERROR: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
