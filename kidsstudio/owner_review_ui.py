"""Opt-in owner-only local private-preview review service (M24).

This deliberately does NOT turn the existing read-only dashboard into a
write endpoint. Binds to loopback, requires an independently configured
owner token for all API calls, enforces Origin on writes, uses strict JSON
shapes and never calls the YouTube API or changes video visibility.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
from typing import Any
from urllib.parse import urlsplit

from .private_preview_review import PreviewReview, PreviewReviewError
from .studio_queue import StudioQueue

MAX_POST_BYTES = 4800
OWNER_ENV = re.compile(r"^[A-Z][A-Z0-9_]{4,90}$")


def make_handler(ledger: PreviewReview, token: str):
    # M63 recovery previews use a separate ledger and NEVER impersonate
    # a completed original episode render. Same local owner token/UI.
    from .recovery_owner_review import RecoveryOwnerReview
    recovered=RecoveryOwnerReview(ledger.queue)
    if not isinstance(token, str) or len(token) < 32:
        raise PreviewReviewError("Private owner session token must be 32+ characters.")

    class ReviewHandler(BaseHTTPRequestHandler):
        server_version = "KidsStudioOwnerReview/1.0"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:
            # URLs, owner notes, tokens or video IDs must not be logged.
            return

        def _reply(self, code: int, data: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code: int, data: dict | list) -> None:
            self._reply(code, json.dumps(data, ensure_ascii=False,
                separators=(",", ":"), allow_nan=False).encode("utf-8"),
                "application/json; charset=utf-8")

        def _safe_host(self) -> bool:
            host=self.headers.get("Host", "")
            return host in (f"127.0.0.1:{self.server.server_port}",
                            f"localhost:{self.server.server_port}")

        def _auth(self) -> bool:
            supplied=self.headers.get("Authorization", "")
            return (supplied.startswith("Bearer ") and
                    secrets.compare_digest(supplied[7:], token))

        def do_GET(self) -> None:
            if not self._safe_host():
                self._json(403,{"error":"HOST_FORBIDDEN"})
                return
            url=urlsplit(self.path)
            if url.query or url.fragment:
                self._json(400,{"error":"QUERY_DISABLED"})
                return
            if url.path in ("/","/index.html","/owner-review.js","/owner-review.css"):
                filename={"/":"owner-review.html",
                          "/index.html":"owner-review.html",
                          "/owner-review.js":"owner-review.js",
                          "/owner-review.css":"owner-review.css"}[url.path]
                mime=("text/html; charset=utf-8" if filename.endswith(".html")
                      else "text/css; charset=utf-8" if filename.endswith(".css")
                      else "application/javascript; charset=utf-8")
                asset=Path(__file__).parent/"dashboard_assets"/filename
                if not asset.is_file():
                    self._json(503,{"error":"ASSET_UNAVAILABLE"})
                    return
                self._reply(200,asset.read_bytes(),mime)
                return
            if url.path not in ("/api/previews","/api/candidates","/api/health"):
                self._json(404,{"error":"NOT_FOUND"})
                return
            if not self._auth():
                self._json(401,{"error":"OWNER_TOKEN_REQUIRED"})
                return
            try:
                if url.path=="/api/previews":
                    data=ledger.snapshot()
                    additional=recovered.snapshot()
                    data["previews"]+=additional["previews"]
                    data["previews"].sort(
                        key=lambda x:x["recorded_at"],reverse=True)
                    data["pending_review"]+=additional["pending_review"]
                    data["revision_requests"]+=additional["revision_requests"]
                    data["recovery_video_reviews"]=len(additional["previews"])
                elif url.path=="/api/candidates":
                    data={"candidates":ledger.candidates()}
                else:
                    data={"status":"ready","local_owner_only":True,
                          "youtube_connected":False}
            except (PreviewReviewError, ValueError, OSError):
                self._json(409,{"error":"REVIEW_LEDGER_UNAVAILABLE"})
                return
            self._json(200,data)

        def do_POST(self) -> None:
            if not self._safe_host():
                self._json(403,{"error":"HOST_FORBIDDEN"})
                return
            url=urlsplit(self.path)
            if url.query or url.fragment or url.path not in (
                "/api/private-upload","/api/comment","/api/decision"):
                self._json(404,{"error":"NOT_FOUND"})
                return
            # Site-origin check + explicit owner bearer: malicious websites
            # cannot issue authenticated cross-origin writes with cookies.
            if (self.headers.get("Origin")!=
                    "http://"+self.headers.get("Host","") or
                    self.headers.get("X-KidsStudio-Owner-Action")!="yes"):
                self._json(403,{"error":"ORIGIN_OR_ACTION_FORBIDDEN"})
                return
            if not self._auth():
                self._json(401,{"error":"OWNER_TOKEN_REQUIRED"})
                return
            length=self.headers.get("Content-Length", "")
            if (self.headers.get("Content-Type")!="application/json"
                    or not length.isdecimal() or not 2 <= int(length) <= MAX_POST_BYTES):
                self._json(400,{"error":"INVALID_JSON_BODY"})
                return
            try:
                body=json.loads(self.rfile.read(int(length)))
                if not isinstance(body,dict):
                    raise PreviewReviewError("JSON object required.")
                if url.path=="/api/private-upload":
                    if set(body)!={"series_id","episode_number","video_id",
                                   "render_job_id","master_sha256"}:
                        raise PreviewReviewError("Unexpected private upload fields.")
                    result=ledger.record_private_upload(**body)
                elif url.path=="/api/comment":
                    if set(body)!={"video_id","text","category","second"}:
                        raise PreviewReviewError("Unexpected feedback fields.")
                    target=(recovered if recovered.has_video(body["video_id"])
                            else ledger)
                    result=target.add_comment(**body)
                else:
                    if set(body)!={"video_id","decision","note"}:
                        raise PreviewReviewError("Unexpected owner decision fields.")
                    target=(recovered if recovered.has_video(body["video_id"])
                            else ledger)
                    result=target.decide(**body)
            except (PreviewReviewError, ValueError, TypeError, KeyError):
                self._json(409,{"error":"OWNER_ACTION_REJECTED_CHECK_CURRENT_STATE"})
                return
            self._json(200,result)

        def do_PUT(self): self._json(405,{"error":"METHOD_FORBIDDEN"})
        do_PATCH=do_DELETE=do_PUT

    return ReviewHandler


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(prog="studio-owner-review",
        description="Owner private-upload comments/approvals, local-only.")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--port",type=int,default=8794)
    p.add_argument("--token-env",default="KIDS_STUDIO_OWNER_REVIEW_TOKEN")
    args=p.parse_args(argv)
    if not OWNER_ENV.fullmatch(args.token_env) or not 1024 <= args.port <= 65535:
        p.error("Invalid token environment name or port.")
    token=os.environ.get(args.token_env,"")
    if len(token)<32:
        p.error("Owner token must be 32+ characters in a private environment variable.")
    try:
        ledger=PreviewReview(StudioQueue(args.db))
        # Owner must explicitly initialize additive schema via CLI first.
        with ledger.queue._connection() as db:
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                    AND name='studio_private_previews'""").fetchone():
                raise PreviewReviewError("Initialize M24 review schema first.")
        server=ThreadingHTTPServer(("127.0.0.1",args.port),make_handler(ledger,token))
        print("Owner private-review UI: http://127.0.0.1:"+str(args.port)+"/",
              flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            server.server_close()
        return 0
    except (OSError,ValueError) as exc:
        print("OWNER_REVIEW_UNAVAILABLE: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
