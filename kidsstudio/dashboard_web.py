"""Loopback-only read-only dashboard HTTP endpoint.

Single-process local operator preview; no auth or remote access is provided.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
from urllib.parse import urlsplit, parse_qs

from .episode_notes import EpisodeNotes
from .video_review_history import VideoReviewHistory
from .review_freshness import project_review_freshness
from .episode_review_overview import build_episode_review_overview
from .verified_episode_review import build_verified_episode_review

from .dashboard_summary import build_dashboard_summary
from .queue_dashboard import queue_dashboard_snapshot

_HTML = """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KidsStudio | لوحة الإنتاج</title>
<style>
body{font-family:system-ui,sans-serif;background:#101827;color:#f4f7ff;margin:0;padding:2rem}
main{max-width:940px;margin:auto}h1{margin-bottom:.3rem}
small,p{color:#bdc9dd}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:1rem;margin-top:2rem}
article{background:#202c40;border:1px solid #394760;border-radius:15px;padding:1.25rem}
strong{font-size:2.1rem;display:block;margin-top:.7rem}
.status{margin-top:1rem;padding:1rem;background:#26354a;border-radius:12px}
</style></head><body><main>
<h1>KidsStudio — لوحة الإنتاج</h1>
<p>معاينة محلية للقراءة فقط. لا توجد صلاحية تشغيل أو رفع أو نشر.</p>
<div class="status" id="status" role="status">جاري قراءة حالة الطابور...</div>
<section class="cards" id="cards" aria-label="إحصائيات المهام"></section>
<section id="reviews-section" hidden style="margin-top:2rem;background:#202c40;border-radius:15px;padding:1.25rem">
<h2>تاريخ مراجعات الفيديو</h2><p>كل مراجعة مرتبطة ببصمة نسخة الفيديو — للقراءة فقط.</p>
<form id="reviews-form"><label for="review-episode-id">معرّف الحلقة</label>
<input id="review-episode-id" required maxlength="80" pattern="[A-Za-z0-9][A-Za-z0-9_-]*">
<button type="submit">عرض تاريخ النسخ</button></form>
<p id="reviews-status" role="status"></p><ol id="reviews-list"></ol></section>
<section id="notes-section" hidden style="margin-top:2rem;background:#202c40;border-radius:15px;padding:1.25rem">
<h2>ملاحظات الحلقات</h2><p>للقراءة فقط — إغلاق الملاحظات لا يمنح موافقة النشر.</p>
<form id="notes-form"><label for="episode-id">معرّف الحلقة</label>
<input id="episode-id" required maxlength="80" pattern="[A-Za-z0-9][A-Za-z0-9_-]*">
<button type="submit">عرض الملاحظات</button></form>
<p id="notes-status" role="status"></p><ul id="notes-list"></ul></section>
<script>
const labels=[["waiting","بانتظار التنفيذ"],["running","قيد التنفيذ"],["completed","مكتملة"],["needs_attention","تحتاج معالجة"],["cancelled","ملغاة"]];
fetch("/api/summary",{cache:"no-store"}).then(async r=>{if(!r.ok)throw Error("unavailable");return r.json()}).then(d=>{
 document.getElementById("status").textContent=d.queue_paused?"الطابور متوقف مؤقتاً":"الطابور متاح — بيانات للعرض فقط";
 const cards=document.getElementById("cards");
 for(const [key,label] of labels){const a=document.createElement("article");
 const t=document.createElement("span");t.textContent=label;
 const v=document.createElement("strong");v.textContent=String(d[key]);
 a.append(t,v);cards.append(a)}
}).catch(()=>{document.getElementById("status").textContent="تعذرت قراءة قاعدة البيانات؛ لا توجد صلاحية لإجراء تغييرات."});
const reviewsSection=document.getElementById("reviews-section");
if(__REVIEWS_ENABLED__){
 reviewsSection.hidden=false;
 document.getElementById("reviews-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const id=document.getElementById("review-episode-id").value;
  const status=document.getElementById("reviews-status");
  const list=document.getElementById("reviews-list");
  list.replaceChildren();
  if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(id)){status.textContent="معرّف الحلقة غير صالح";return;}
  status.textContent="جاري قراءة المراجعات...";
  try{
   const response=await fetch("/api/reviews?episode_id="+encodeURIComponent(id),{cache:"no-store"});
   if(!response.ok)throw Error("unavailable");
   const data=await response.json();
   if(data.status!=="REVIEWS_READ_ONLY"||!Array.isArray(data.reviews))throw Error("invalid");
   status.textContent=data.reviews.length?"عدد المراجعات: "+data.reviews.length:"لا توجد مراجعات";
   for(const review of data.reviews){
    const li=document.createElement("li");
    li.style.whiteSpace="pre-wrap";li.style.overflowWrap="anywhere";
    const label=document.createElement("strong");
    label.textContent="مراجعة "+review.review_id+" — "+review.review_outcome+" — SHA256: "+review.video_sha256.slice(0,12)+"… ";
    const body=document.createElement("span");body.textContent=review.reviewer_notes;
    li.append(label,body);list.append(li);
   }
  }catch(_){status.textContent="تعذرت قراءة تاريخ المراجعات";list.replaceChildren();}
 });
}
const section=document.getElementById("notes-section");
if(__NOTES_ENABLED__){
 section.hidden=false;
 document.getElementById("notes-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const id=document.getElementById("episode-id").value;
  const status=document.getElementById("notes-status");
  const list=document.getElementById("notes-list");
  list.replaceChildren();
  if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(id)){status.textContent="معرّف الحلقة غير صالح";return;}
  status.textContent="جاري القراءة...";
  try{
   const response=await fetch("/api/notes?episode_id="+encodeURIComponent(id),{cache:"no-store"});
   if(!response.ok)throw Error("unavailable");
   const data=await response.json();
   if(data.status!=="NOTES_READ_ONLY"||!Array.isArray(data.notes))throw Error("invalid");
   status.textContent=data.notes.length?"عدد الملاحظات: "+data.notes.length:"لا توجد ملاحظات";
   for(const note of data.notes){
    const li=document.createElement("li");
    li.style.whiteSpace="pre-wrap";li.style.overflowWrap="anywhere";
    const state=document.createElement("strong");
    state.textContent=note.resolved?"تمت المعالجة — ":"بانتظار المعالجة — ";
    const body=document.createElement("span");body.textContent=note.text;
    li.append(state,body);list.append(li);
   }
  }catch(_){status.textContent="تعذرت قراءة الملاحظات";list.replaceChildren();}
 });
}
</script></main></body></html>"""


def make_handler(database: str, notes_database: str | None = None,
                 reviews_database: str | None = None,
                 video_root: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                data = (_HTML.replace("__NOTES_ENABLED__", "true" if notes_database is not None else "false")
                        .replace("__REVIEWS_ENABLED__", "true" if reviews_database is not None else "false")).encode("utf-8")
                content_type = "text/html; charset=utf-8"
                code = 200
            elif self.path == "/api/summary":
                try:
                    report = build_dashboard_summary(queue_dashboard_snapshot(database))
                    code = 200
                except (OSError, ValueError, TypeError, __import__("sqlite3").Error):
                    report = {"status": "DASHBOARD_UNAVAILABLE",
                              "queue_mutated": False, "publication_approved": False}
                    code = 503
                data = json.dumps(report, sort_keys=True).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif urlsplit(self.path).path == "/api/notes" and notes_database is not None:
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    if set(query) != {"episode_id"} or len(query["episode_id"]) != 1:
                        raise ValueError("invalid query")
                    notes = EpisodeNotes(notes_database).list_notes(
                        episode_id=query["episode_id"][0])
                    report = {"status": "NOTES_READ_ONLY", "notes": notes,
                              "publication_approved": False}
                    code = 200
                except (OSError, ValueError, sqlite3.Error):
                    report = {"status": "NOTES_UNAVAILABLE",
                              "publication_approved": False}
                    code = 503
                data = json.dumps(report, ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif urlsplit(self.path).path == "/api/reviews" and reviews_database is not None:
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    if set(query) != {"episode_id"} or len(query["episode_id"]) != 1:
                        raise ValueError("invalid query")
                    reviews = VideoReviewHistory(reviews_database).list_reviews(
                        episode_id=query["episode_id"][0])
                    report = {"status": "REVIEWS_READ_ONLY", "reviews": reviews,
                              "owner_publication_approval": False}
                    code = 200
                except (OSError, ValueError, sqlite3.Error):
                    report = {"status": "REVIEWS_UNAVAILABLE",
                              "owner_publication_approval": False}
                    code = 503
                data = json.dumps(report, ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif urlsplit(self.path).path == "/api/review-freshness" and reviews_database is not None:
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    if set(query) != {"episode_id", "current_sha256"} or any(
                        len(values) != 1 for values in query.values()
                    ):
                        raise ValueError("invalid query")
                    reviews = VideoReviewHistory(reviews_database).list_reviews(
                        episode_id=query["episode_id"][0])
                    report = project_review_freshness(
                        reviews, current_video_sha256=query["current_sha256"][0])
                    report["current_sha_supplied_by_caller_not_verified"] = True
                    code = 200
                except (OSError, ValueError, sqlite3.Error):
                    report = {"status": "REVIEW_FRESHNESS_UNAVAILABLE",
                              "owner_publication_approval": False}
                    code = 503
                data = json.dumps(report, sort_keys=True).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif (urlsplit(self.path).path == "/api/episode-review"
                  and reviews_database is not None and notes_database is not None):
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    if set(query) != {"episode_id", "current_sha256"} or any(
                        len(values) != 1 for values in query.values()
                    ):
                        raise ValueError("invalid query")
                    report = build_episode_review_overview(
                        episode_id=query["episode_id"][0],
                        current_video_sha256=query["current_sha256"][0],
                        notes_database=notes_database,
                        reviews_database=reviews_database)
                    code = 200
                except (OSError, ValueError, sqlite3.Error):
                    report = {"status": "EPISODE_REVIEW_UNAVAILABLE",
                              "owner_publication_approval": False}
                    code = 503
                data = json.dumps(report, sort_keys=True).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif (urlsplit(self.path).path == "/api/verified-episode-review"
                  and reviews_database is not None and notes_database is not None
                  and video_root is not None):
                try:
                    query = parse_qs(urlsplit(self.path).query, strict_parsing=True)
                    required = {"episode_id", "relative_path", "expected_sha256"}
                    if set(query) != required or any(len(values) != 1 for values in query.values()):
                        raise ValueError("invalid query")
                    report = build_verified_episode_review(
                        episode_id=query["episode_id"][0],
                        video_root=video_root,
                        relative_path=query["relative_path"][0],
                        expected_sha256=query["expected_sha256"][0],
                        notes_database=notes_database,
                        reviews_database=reviews_database)
                    code = 200
                except (OSError, ValueError, sqlite3.Error):
                    report = {"status": "VERIFIED_EPISODE_REVIEW_UNAVAILABLE",
                              "owner_publication_approval": False}
                    code = 503
                data = json.dumps(report, sort_keys=True).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            self.send_error(405)

        def log_message(self, format, *args):
            return

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-only read-only KidsStudio dashboard")
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--notes-db", default=None)
    parser.add_argument("--reviews-db", default=None)
    parser.add_argument("--video-root", default=None)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.db, args.notes_db, args.reviews_db, args.video_root))
    try:
        print(f"Read-only dashboard: http://127.0.0.1:{args.port}/", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
