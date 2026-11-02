"""Loopback-only owner review form. Never expose directly to the network."""
from __future__ import annotations

import argparse
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
from urllib.parse import parse_qs

from .owner_review_store import OwnerReviewStore
from .owner_review_media import load_registry, video_mime
from .owner_video_range import parse_range
from .owner_video_reviews import STATES, _validate_id, _validate_note

MAX_BODY = 4096

def page(episode: str, token: str, state: str = "needs_review", message: str = "", has_video: bool = False) -> bytes:
    _validate_id(episode)
    if state not in STATES:
        raise ValueError("invalid review state")
    options = "".join(
        '<option value="' + escape(value, quote=True) + '"' +
        (' selected' if value == state else '') + '>' + escape(value) + '</option>'
        for value in sorted(STATES)
    )
    video = ('<video controls playsinline preload="metadata" src="/video" style="width:100%;max-width:100%"></video>' if has_video else '')
    return ('''<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'">
<title>Kids Studio — مراجعة الحلقة</title>
<style>body{font-family:system-ui;max-width:600px;margin:2rem auto;padding:1rem}
label{display:block;margin:1rem 0}textarea,select,button{box-sizing:border-box;width:100%;padding:.8rem;font:inherit}
textarea{min-height:8rem}button{margin-top:1rem}small{display:block;margin-top:1rem}</style></head><body>
<h1>مراجعة الحلقة</h1><p>''' + escape(episode) + '''</p>''' + video + '''<p role="status">''' + escape(message) + '''</p>
<form method="post" action="/review">
<input type="hidden" name="token" value="''' + escape(token, quote=True) + '''">
<input type="hidden" name="episode" value="''' + escape(episode, quote=True) + '''">
<label>القرار<select name="state">''' + options + '''</select></label>
<label>الملاحظات<textarea name="note" maxlength="2000"></textarea></label>
<button type="submit">حفظ القرار</button></form>
<small>هذه الصفحة تحفظ المراجعة فقط. لا ترفع الفيديو ولا تنشره.</small>
</body></html>''').encode("utf-8")

def make_handler(store: OwnerReviewStore, token: str, episode: str, media: Path | None = None):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, content: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            if self.path == "/video" and media is not None:
                size = media.stat().st_size
                try:
                    start, end, partial = parse_range(self.headers.get("Range"), size)
                except ValueError:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", video_mime(media))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                with media.open("rb") as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = stream.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                return
            if self.path != "/":
                self._send(404, b"Not found")
                return
            latest = store.latest().get(episode, {})
            self._send(200, page(episode, token, latest.get("state", "needs_review"), has_video=media is not None))

        def do_POST(self) -> None:
            if self.path != "/review":
                self._send(404, b"Not found")
                return
            try:
                size = int(self.headers.get("Content-Length", "-1"))
                if not 0 <= size <= MAX_BODY:
                    raise ValueError("invalid body size")
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/x-www-form-urlencoded":
                    raise ValueError("invalid content type")
                data = parse_qs(self.rfile.read(size).decode("utf-8"), strict_parsing=True)
                if any(len(v) != 1 for v in data.values()):
                    raise ValueError("duplicate field")
                get = lambda name: data[name][0]
                if not secrets.compare_digest(get("token"), token) or get("episode") != episode:
                    raise ValueError("invalid form token or episode")
                state, note = get("state"), data.get("note", [""])[0]
                _validate_note(note)
                if state not in STATES:
                    raise ValueError("invalid state")
                store.record(episode_id=episode, state=state, note=note)
            except (ValueError, KeyError, UnicodeDecodeError):
                self._send(400, b"Invalid request")
                return
            self._send(200, page(episode, token, state, "تم حفظ قرار المراجعة", has_video=media is not None))

    return Handler

def main() -> None:
    parser = argparse.ArgumentParser(description="Loopback-only review form; not phone-accessible")
    parser.add_argument("--db", required=True)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--media-root")
    parser.add_argument("--media-registry")
    args = parser.parse_args()
    _validate_id(args.episode)
    store = OwnerReviewStore(Path(args.db))
    store.initialize()
    if bool(args.media_root) != bool(args.media_registry):
        parser.error("--media-root and --media-registry must be supplied together")
    media = load_registry(args.media_registry, args.media_root).get(args.episode) if args.media_root else None
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store, token, args.episode, media))
    print(f"Open on this computer only: http://127.0.0.1:{server.server_port}/", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
