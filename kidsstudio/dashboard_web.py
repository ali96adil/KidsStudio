"""Loopback-only read-only dashboard HTTP endpoint.

Single-process local operator preview; no auth or remote access is provided.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

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
</script></main></body></html>"""


def make_handler(database: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                data = _HTML.encode("utf-8")
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
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.db))
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
