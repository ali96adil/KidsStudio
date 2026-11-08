"""Opt-in mobile-friendly PRIVATE draft web UI, strictly Pi loopback-only.

No Internet/Google/SSH exposure, video streaming, source mutation, upload,
publication or background service. Bound ONLY to 127.0.0.1; for a phone,
use an authenticated SSH tunnel rather than exposing a raw Wi-Fi port.

A random session-only Basic password is generated per invocation. CSRF and
Origin checks protect the only write: the existing exact-journal/SHA-bound
append-only private review note. A browser assertion is NOT proof that a
human watched the video or permission to make a video public.
"""
from __future__ import annotations

import argparse
import base64
from html import escape
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs

from .optional_tool_evidence import read_private_json
from .pi_private_draft_inbox import build_private_draft_inbox
from .pi_private_draft_review import record_post_private_draft_review

_LOOPBACK = "127.0.0.1"
_PORT = 8844
_MAX_FORM_BYTES = 8192
_JOURNAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.json\Z")
_STATUS = {
    "NEEDS_OWNER_REVIEW_PRIVATE": ("بانتظار المراجعة", "pending"),
    "REVISION_REQUIRED_PRIVATE": ("يحتاج تعديل", "revision"),
    "ACCEPTED_PRIVATE_ONLY": ("مقبول كمسودة خاصة", "accepted"),
    "UPLOAD_UNCONFIRMED": ("الرفع غير مؤكد", "uncertain"),
    "BLOCKED_LOCAL_EVIDENCE": ("البيانات تحتاج فحص", "blocked"),
}
_EDITABLE = frozenset({
    "NEEDS_OWNER_REVIEW_PRIVATE",
    "REVISION_REQUIRED_PRIVATE",
    "ACCEPTED_PRIVATE_ONLY",
})

_CSS = r"""
:root{color-scheme:dark;--bg:#0d1423;--panel:#172338;--line:#30435a;
--text:#edf5ff;--sub:#c0d1e3;--accent:#85caff}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--text);font:16px/1.65 system-ui,
-apple-system,"Noto Sans Arabic",sans-serif;margin:0}
main{max-width:980px;margin:auto;padding:22px 15px 52px}
header{display:flex;justify-content:space-between;align-items:center;
gap:12px;flex-wrap:wrap}
h1{font-size:clamp(23px,5vw,34px);margin:0}
h2{font-size:20px;margin:0 0 8px}
p{margin:8px 0;color:var(--sub)}
a{color:#a6d8ff}
a.refresh{border:1px solid var(--line);background:var(--panel);
border-radius:11px;padding:9px 17px;text-decoration:none;color:var(--text)}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(138px,1fr));
gap:10px;margin:20px 0}
.metric{padding:15px;border:1px solid var(--line);background:var(--panel);
border-radius:14px}
.metric strong{display:block;font-size:27px}
.metric span{font-size:13px;color:var(--sub)}
section.drafts{display:grid;gap:15px}
article{background:var(--panel);border:1px solid var(--line);
border-radius:16px;padding:18px;overflow-wrap:anywhere}
.heading{display:flex;justify-content:space-between;align-items:flex-start;
flex-wrap:wrap;gap:10px}
.tag{font-weight:600;border-radius:8px;border:1px solid #54718e;
padding:4px 9px;font-size:13px}
.tag.revision,.tag.blocked{color:#ffd0ce;border-color:#ca8585}
.tag.pending,.tag.uncertain{color:#ffe6aa;border-color:#ba945c}
.tag.accepted{color:#b3f2d3;border-color:#599b80}
.small{font-size:13px;color:var(--sub)}
form{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}
label{display:block;margin:10px 0}
select,textarea,button{font:inherit;max-width:100%;border-radius:9px}
select,textarea{width:100%;padding:10px;border:1px solid #65829b;
background:#0e1928;color:var(--text)}
textarea{min-height:90px;resize:vertical}
label.check{display:flex;gap:11px;align-items:flex-start}
input[type=checkbox]{width:18px;height:18px;flex:none;margin-top:4px}
button{padding:11px 20px;border:0;background:#89ccf5;color:#102235;
font-weight:700;cursor:pointer}
.notice{border:1px solid var(--line);padding:13px;border-radius:12px;
margin:16px 0;background:#162638}
.done{border-color:#63a889}
footer{margin-top:24px;border-top:1px solid var(--line);padding-top:15px}
"""


def render_mobile_dashboard(report: dict, *, csrf: str,
                            saved: bool = False) -> str:
    """Safe server-only HTML, no JS/CDN/external image requests."""
    if report.get("status") != "PI_PRIVATE_DRAFT_INBOX_READ_ONLY":
        raise ValueError("Offline draft evidence not ready.")
    if not isinstance(csrf, str) or not 24 <= len(csrf) <= 128:
        raise ValueError("Missing browser session CSRF nonce.")
    nonce = escape(csrf, quote=True)
    counts = report["counts"]
    metrics = [
        ("بانتظار مراجعتك", "NEEDS_OWNER_REVIEW_PRIVATE"),
        ("تحتاج تعديل", "REVISION_REQUIRED_PRIVATE"),
        ("مقبولة PRIVATE", "ACCEPTED_PRIVATE_ONLY"),
        ("رفع غير مؤكد", "UPLOAD_UNCONFIRMED"),
        ("تحتاج فحص", "BLOCKED_LOCAL_EVIDENCE"),
    ]
    fragments = [
        '<!doctype html><html lang="ar" dir="rtl"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="referrer" content="no-referrer">',
        '<title>KidsStudio | مراجعة المسودات الخاصة</title>',
        f'<style nonce="{nonce}">{_CSS}</style></head><body><main>',
        '<header><h1>KidsStudio — المسودات الخاصة</h1>'
        '<a class="refresh" href="/">تحديث الحالة</a></header>',
        '<p>عرض محلي مشفّر أثناء نفق SSH فقط؛ السجلات تاريخية وليست '
        'فحصاً مباشراً لحالة يوتيوب.</p>',
    ]
    if saved:
        fragments.append(
            '<div class="notice done" role="status">'
            'تم حفظ الملاحظة محلياً للنسخة المحددة؛ لا نشر عام.</div>')
    fragments.append('<div class="summary">')
    for title, status in metrics:
        number = counts[status]
        fragments.append(
            f'<div class="metric"><strong>{number}</strong>'
            f'<span>{escape(title)}</span></div>')
    fragments.append('</div><section class="drafts">')
    for row in report["items"]:
        status = row["status"]
        title, css_class = _STATUS[status]
        journal = row.get("journal_name")
        episode = row.get("episode_id")
        movie = row.get("video_name")
        fragments.extend([
            '<article>',
            '<div class="heading"><div>',
            f'<h2>{escape(str(episode or "مسودة غير مؤكدة"))}</h2>',
            f'<div class="small">السجل: {escape(str(journal or "غير آمن"))}</div>',
            '</div>',
            f'<span class="tag {css_class}">{escape(title)}</span></div>',
        ])
        if movie:
            fragments.append(
                f'<p class="small">الملف المحلي: {escape(str(movie))}</p>')
        fragments.append(
            '<p class="small">ملاحظات قبول: '
            f'{int(row["matching_acceptance_notes"])} — '
            'طلبات تعديل: '
            f'{int(row["matching_revision_notes"])}</p>')
        if (status in _EDITABLE and isinstance(journal, str)
                and _JOURNAL.fullmatch(journal)):
            fragments.extend([
                '<form action="/review" method="post" accept-charset="UTF-8">',
                f'<input type="hidden" name="csrf" value="{nonce}">',
                f'<input type="hidden" name="journal" '
                f'value="{escape(journal, quote=True)}">',
                '<label>قرارك لهذه النسخة'
                '<select name="outcome">'
                '<option value="REVISION_REQUIRED">تحتاج تعديل</option>'
                '<option value="ACCEPTED_PRIVATE">مقبولة كمسودة PRIVATE</option>'
                '</select></label>',
                '<label>ملاحظات المراجعة'
                '<textarea name="notes" maxlength="2000" '
                'placeholder="اكتب الملاحظات أو التعديلات المطلوبة هنا"></textarea>'
                '</label>',
                '<label class="check">'
                '<input type="checkbox" name="private_checked" value="yes">'
                '<span>شاهدت المسودة الخاصة المحددة في YouTube Studio '
                'وتأكدت يدوياً أنها PRIVATE</span></label>',
                '<label class="check">'
                '<input type="checkbox" name="full_checked" value="yes">'
                '<span>شاهدت الفيديو بالكامل (مطلوب للقبول)</span></label>',
                '<label class="check">'
                '<input type="checkbox" name="arabic_checked" value="yes">'
                '<span>استمعت لكل الصوت العربي (مطلوب للقبول)</span></label>',
                '<button type="submit">احفظ المراجعة محلياً</button>',
                '</form>',
            ])
        else:
            fragments.append(
                '<p class="small">هذه النسخة غير مؤهلة لحفظ مراجعة '
                'من الواجهة؛ افحص السجل الأصلي أولاً.</p>')
        fragments.append('</article>')
    if not report["items"]:
        fragments.append(
            '<article><h2>ماكو مسودات مسجلة حالياً</h2>'
            '<p>اللوحة لا تبدأ أي رفع تلقائي.</p></article>')
    fragments.extend([
        '</section><footer><p>مهم: القبول هنا للنسخة PRIVATE فقط. '
        'الملاحظات تصريحات من المشغّل وليست إثبات هوية. '
        'لا تفويض للنشر العام، ولا اتصال بخوادم Google من هذه الواجهة.</p>'
        '<p>لا تفتح منفذ الصفحة مباشرة على شبكة Wi-Fi؛ '
        'استعمل نفق SSH خاص ومصادق عليه.</p></footer>',
        '</main></body></html>',
    ])
    return "".join(fragments)


def make_private_dashboard_handler(*, journal_root: str, private_root: str,
                                   review_root: str, password: str,
                                   csrf: str, port: int) -> type[BaseHTTPRequestHandler]:
    """Authenticated localhost-only handler for injected HTTPServer in tests."""
    if (not isinstance(password, str) or len(password) < 24
            or not isinstance(csrf, str) or len(csrf) < 24
            or type(port) is not int or not 0 <= port <= 65535):
        raise ValueError("Invalid local-only dashboard session.")
    expected_auth = (
        "Basic " + base64.b64encode(
            ("owner:" + password).encode("utf-8")).decode("ascii"))
    valid_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    valid_origins = {"http://" + host for host in valid_hosts}

    class PrivateDashboardHandler(BaseHTTPRequestHandler):
        server_version = "KidsStudio-Private"
        sys_version = ""

        def log_message(self, fmt, *args):
            # NO HTTP request, URLs, cookies, Basic credentials or notes
            # are written to logs. No remote access should be possible.
            pass

        def _send(self, status: int, payload: bytes, *,
                  content_type: str = "text/plain; charset=utf-8",
                  extra: dict[str, str] | None = None,
                  body: bool = True) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; "
                f"style-src 'nonce-{csrf}'; "
                "form-action 'self'; frame-ancestors 'none'; "
                "base-uri 'none'; object-src 'none'; connect-src 'none'; "
                "img-src 'none'; script-src 'none'",
            )
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(payload)

        def _gate(self) -> bool:
            if self.headers.get("Host") not in valid_hosts:
                self._send(421, b"Local host only.")
                return False
            auth = self.headers.get("Authorization", "")
            if (not isinstance(auth, str) or len(auth) > 256
                    or not hmac.compare_digest(auth, expected_auth)):
                self._send(
                    401, b"Session password required.",
                    extra={"WWW-Authenticate":
                           'Basic realm="KidsStudio Private Drafts", charset="UTF-8"'})
                return False
            return True

        def _dashboard(self, *, head: bool = False):
            if not self._gate():
                return
            if self.path not in ("/", "/?saved=1"):
                self._send(404, b"Not found.")
                return
            try:
                snapshot = build_private_draft_inbox(
                    journal_root=journal_root, private_root=private_root,
                    review_root=review_root)
                html = render_mobile_dashboard(
                    snapshot, csrf=csrf, saved=self.path == "/?saved=1")
                content = html.encode("utf-8")
            except (ValueError, OSError, TypeError, KeyError):
                self._send(503, b"Private local evidence not ready.")
                return
            self._send(
                200, content, content_type="text/html; charset=utf-8",
                body=not head)

        def do_GET(self):
            self._dashboard()

        def do_HEAD(self):
            self._dashboard(head=True)

        def do_POST(self):
            if not self._gate():
                return
            if self.path != "/review":
                self._send(404, b"Not found.")
                return
            if self.headers.get("Origin") not in valid_origins:
                self._send(403, b"Untrusted browser origin.")
                return
            if (self.headers.get("Content-Type") != "application/x-www-form-urlencoded"
                    or self.headers.get("Transfer-Encoding") is not None):
                self._send(415, b"Only small local browser forms allowed.")
                return
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdigit():
                self._send(411, b"Form length required.")
                return
            size = int(length)
            if not 1 <= size <= _MAX_FORM_BYTES:
                self._send(413, b"Form too large.")
                return
            try:
                values = parse_qs(
                    self.rfile.read(size).decode("utf-8", "strict"),
                    keep_blank_values=True, strict_parsing=True,
                    max_num_fields=7)
                required = {"csrf", "journal", "outcome", "notes"}
                optional = {"private_checked", "full_checked", "arabic_checked"}
                if not required.issubset(values) or set(values) - required - optional:
                    raise ValueError("Invalid form fields.")
                if any(len(field) != 1 for field in values.values()):
                    raise ValueError("Duplicate form field.")
                if not hmac.compare_digest(values["csrf"][0], csrf):
                    self._send(403, b"Invalid browser form token.")
                    return
                journal = values["journal"][0]
                outcome = values["outcome"][0]
                notes = values["notes"][0]
                if not _JOURNAL.fullmatch(journal):
                    raise ValueError("Invalid journal selector.")
                if outcome not in ("REVISION_REQUIRED", "ACCEPTED_PRIVATE"):
                    raise ValueError("Invalid review outcome.")
                if len(notes) > 2000:
                    raise ValueError("Review notes too long.")
                checks = {
                    name: name in values and values[name] == ["yes"]
                    for name in optional
                }
                if any(
                    name in values and not checks[name] for name in optional
                ):
                    raise ValueError("Invalid review checkbox.")
                snapshot = build_private_draft_inbox(
                    journal_root=journal_root, private_root=private_root,
                    review_root=review_root, show_video_ids=True)
                eligible = [
                    row for row in snapshot["items"]
                    if row["journal_name"] == journal and row["status"] in _EDITABLE
                ]
                if len(eligible) != 1:
                    raise ValueError("Cannot review an unconfirmed draft.")
                local = read_private_json(journal_root, journal)
                row = eligible[0]
                if (row["episode_id"] != local.get("episode_id")
                        or row["video_name"] != local.get("media_name")
                        or row["youtube_video_id"] != local.get("video_id")):
                    raise ValueError("Changed journal during selection.")
                record_post_private_draft_review(
                    private_root=private_root,
                    relative_path=local["media_name"],
                    expected_sha256=local["media_sha256"],
                    episode_id=local["episode_id"],
                    journal_file=str(Path(journal_root) / journal),
                    video_id=local["video_id"],
                    review_root=review_root,
                    review_outcome=outcome,
                    reviewer_notes=notes,
                    reviewed_private_youtube_draft=checks["private_checked"],
                    reviewed_full_video=checks["full_checked"],
                    reviewed_arabic_voice=checks["arabic_checked"],
                    save_review=True,
                )
            except (ValueError, OSError, TypeError, KeyError, UnicodeError):
                self._send(422, b"Review not saved; check the exact PRIVATE draft.")
                return
            self._send(
                303, b"", extra={"Location": "/?saved=1"})

        def do_PUT(self):
            self._send(405, b"Unsupported method.")

        def do_DELETE(self):
            self._send(405, b"Unsupported method.")

        def do_OPTIONS(self):
            self._send(405, b"Unsupported method.")

    return PrivateDashboardHandler


def serve_private_dashboard(*, journal_root: str, private_root: str,
                            review_root: str, port: int = _PORT) -> None:
    """Foreground service only: no daemon, no LAN exposure, no persisted auth."""
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Choose an unprivileged loopback port.")
    build_private_draft_inbox(
        journal_root=journal_root, private_root=private_root,
        review_root=review_root)
    password = secrets.token_urlsafe(28)
    csrf = secrets.token_urlsafe(32)
    handler = make_private_dashboard_handler(
        journal_root=journal_root, private_root=private_root,
        review_root=review_root, password=password,
        csrf=csrf, port=port)
    with HTTPServer((_LOOPBACK, port), handler) as server:
        server.timeout = 5
        print(f"KidsStudio private dashboard: http://{_LOOPBACK}:{port}/", flush=True)
        print("Login username: owner", flush=True)
        print("Local session password (do not share or save in Git):",
              password, flush=True)
        print(
            "Bound ONLY to Pi localhost; use authenticated SSH port forwarding "
            "for a remote browser. Stop with Ctrl+C.", flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Authenticated, Pi localhost-only browser UI for PRIVATE drafts")
    parser.add_argument("--journal-root", default=str(
        Path.home() / "kidsstudio-private" / "journals"))
    parser.add_argument("--private-root", default=str(
        Path.home() / "kidsstudio-private" / "inbox"))
    parser.add_argument("--review-root", default=str(
        Path.home() / "kidsstudio-private" / "reviews"))
    parser.add_argument("--port", type=int, default=_PORT)
    args = parser.parse_args(argv)
    try:
        serve_private_dashboard(
            journal_root=args.journal_root, private_root=args.private_root,
            review_root=args.review_root, port=args.port)
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({
            "status": "PI_PRIVATE_DASHBOARD_BLOCKED",
            "google_or_ssh_network_called": False,
            "publication_approved": False,
        }, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
