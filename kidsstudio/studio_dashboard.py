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
                version FROM studio_private_previews ORDER BY version DESC"""):
                key=(item["series_id"],item["ordinal"])
                if key not in preview_states:
                    preview_states[key]={
                        "video_id":item["video_id"],"state":item["state"],
                        "version":item["version"],
                        "url":"https://www.youtube.com/watch?v="+item["video_id"],
                        "youtube_visibility_verified":False,
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
                    "state":row["state"],"criteria_passed":row["checks_passed"]
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
