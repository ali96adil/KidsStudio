"""Loopback authenticated mobile PRIVATE draft dashboard — no external services."""
from __future__ import annotations

import base64
import hashlib
from http.client import HTTPConnection
from http.server import HTTPServer
import json
from pathlib import Path
from threading import Thread
import tempfile
import unittest
from urllib.parse import urlencode

from kidsstudio.pi_private_draft_web import (
    make_private_dashboard_handler, render_mobile_dashboard,
    serve_private_dashboard,
)
from kidsstudio.pi_private_draft_inbox import build_private_draft_inbox
from kidsstudio.pi_youtube_private_upload import _save_journal


class PrivateDraftWebTests(unittest.TestCase):
    PASSWORD = "CI_password_repeated_for_private_local_tests_12345"
    CSRF = "CI_CSRF_nonce_repeated_for_private_tests_123456"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.journals, self.inbox, self.reviews = (
            base / "journals", base / "inbox", base / "reviews")
        for directory in (self.journals, self.inbox, self.reviews):
            directory.mkdir(mode=0o700)
        self.video_name = "colors_ar_01_v1.mp4"
        self.video = self.inbox / self.video_name
        self.video.write_bytes(b"TEST_ONLY_FAKE_MEDIA" * 300)
        self.video.chmod(0o600)
        self.sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.video_id = "ciPrivateVi65"
        self.journal = self.journals / "colors_v1.json"
        self.state = {
            "schema_version": 1,
            "state": "PRIVATE_UPLOAD_CONFIRMED",
            "intent_sha256": "d"*64,
            "media_sha256": self.sha,
            "media_bytes": self.video.stat().st_size,
            "media_name": self.video.name,
            "episode_id": "colors_ar_01",
            "video_id": self.video_id,
        }
        _save_journal(self.journal, self.state, create=True)
        self.handler = make_private_dashboard_handler(
            journal_root=str(self.journals),
            private_root=str(self.inbox),
            review_root=str(self.reviews),
            password=self.PASSWORD,
            csrf=self.CSRF, port=0)
        self.server = HTTPServer(("127.0.0.1", 0), self.handler)
        self.server.timeout = .5
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.port = self.server.server_port
        self.auth = "Basic " + base64.b64encode(
            ("owner:" + self.PASSWORD).encode()).decode("ascii")
        self.origin = f"http://127.0.0.1:{self.port}"

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, *, auth=True, origin=True,
                host=None, fields=None, content_type=None, data=None):
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if auth:
            headers["Authorization"] = self.auth
        if origin:
            headers["Origin"] = (self.origin if origin is True else origin)
        if fields is not None:
            data = urlencode(fields).encode("utf-8")
            content_type = content_type or "application/x-www-form-urlencoded"
        if content_type:
            headers["Content-Type"] = content_type
        con = HTTPConnection("127.0.0.1", self.port, timeout=8)
        try:
            con.request(method, path, body=data, headers=headers)
            response = con.getresponse()
            content = response.read()
            return response.status, dict(response.getheaders()), content
        finally:
            con.close()

    def fields(self, outcome="REVISION_REQUIRED", notes="صحح لون السماء",
               **extra):
        return {
            "csrf": self.CSRF,
            "journal": self.journal.name,
            "outcome": outcome,
            "notes": notes,
            "private_checked": "yes",
            **extra,
        }

    def notes(self):
        return list(self.reviews.iterdir())

    def status(self):
        return build_private_draft_inbox(
            journal_root=str(self.journals),
            private_root=str(self.inbox),
            review_root=str(self.reviews),
        )["items"][0]["status"]

    def test_real_loopback_binding_and_zero_broad_network_interface(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertNotEqual(self.server.server_address[0], "0.0.0.0")

    def test_unauthorized_browser_denied_no_private_html(self):
        status, headers, body = self.request("GET", "/", auth=False)
        self.assertEqual(status, 401)
        self.assertIn("Basic", headers["WWW-Authenticate"])
        self.assertNotIn(b"colors_ar_01", body)
        self.assertNotIn(self.video_id.encode(), body)
        self.assertNotIn(self.CSRF.encode(), body)
        self.assertEqual(self.notes(), [])

    def test_wrong_basic_password_rejected(self):
        old = self.auth
        try:
            self.auth = "Basic " + base64.b64encode(
                b"owner:incorrect_password").decode("ascii")
            self.assertEqual(self.request("GET", "/")[0], 401)
        finally:
            self.auth = old

    def test_host_header_rebinding_blocked(self):
        for host in ("evil.example", "127.0.0.1:443",
                     f"pi.local:{self.port}",
                     f"localhost:{self.port}.bad.example"):
            with self.subTest(host=host):
                self.assertEqual(
                    self.request("GET", "/", host=host)[0], 421)

    def test_localhost_host_header_is_supported_for_ssh_tunnel(self):
        status, _, body = self.request(
            "GET", "/", host=f"localhost:{self.port}")
        self.assertEqual(status, 200)
        self.assertIn("KidsStudio".encode(), body)

    def test_authenticated_arabic_mobile_html_and_statuses(self):
        status, headers, data = self.request("GET", "/")
        html = data.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn('lang="ar" dir="rtl"', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("بانتظار المراجعة", html)
        self.assertIn("colors_ar_01", html)
        self.assertIn("مقبولة كمسودة PRIVATE", html)
        self.assertIn('method="post"', html)
        self.assertIn('name="csrf"', html)
        self.assertNotIn(self.video_id, html)
        self.assertNotIn(self.sha, html)
        self.assertNotIn(str(self.inbox), html)

    def test_response_protects_from_browser_caching_framing_and_js(self):
        _, headers, _ = self.request("GET", "/")
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        policy = headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", policy)
        self.assertIn("script-src 'none'", policy)
        self.assertIn("form-action 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("style-src 'nonce-", policy)
        self.assertNotIn("Set-Cookie", headers)

    def test_repeated_get_is_read_only(self):
        before = self.journal.read_bytes()
        for _ in range(3):
            self.assertEqual(self.request("GET", "/")[0], 200)
            self.assertEqual(self.request("HEAD", "/")[0], 200)
        self.assertEqual(self.journal.read_bytes(), before)
        self.assertEqual(self.notes(), [])

    def test_csrf_and_cross_origin_posts_block_without_note(self):
        bad = self.fields(csrf="bogus")
        self.assertEqual(self.request("POST", "/review", fields=bad)[0], 403)
        self.assertEqual(
            self.request("POST", "/review",
                         fields=self.fields(), origin=False)[0], 403)
        self.assertEqual(self.notes(), [])

    def test_both_trusted_loopback_hosts_support_same_origin_forms(self):
        # Both 127.0.0.1 and localhost are trusted independently, but a
        # form must originate from the EXACT host used in its browser URL.
        self.assertEqual(
            self.request("POST", "/review",
                         fields=self.fields(),
                         host=f"localhost:{self.port}")[0], 403)
        self.assertEqual(self.notes(), [])
        self.assertEqual(
            self.request("POST", "/review",
                         fields=self.fields(),
                         host=f"localhost:{self.port}",
                         origin=f"http://localhost:{self.port}")[0], 303)
        self.assertEqual(self.status(), "REVISION_REQUIRED_PRIVATE")

    def test_explicit_review_requires_private_draft_checkbox(self):
        form = self.fields()
        form.pop("private_checked")
        self.assertEqual(
            self.request("POST", "/review", fields=form)[0], 422)
        self.assertEqual(self.notes(), [])

    def test_browser_revision_creates_one_private_note_and_changes_dashboard(self):
        self.assertEqual(self.status(), "NEEDS_OWNER_REVIEW_PRIVATE")
        response, headers, _ = self.request(
            "POST", "/review", fields=self.fields())
        self.assertEqual(response, 303)
        self.assertEqual(headers["Location"], "/?saved=1")
        self.assertEqual(self.status(), "REVISION_REQUIRED_PRIVATE")
        self.assertEqual(len(self.notes()), 1)
        item = self.notes()[0]
        self.assertEqual(item.stat().st_mode & 0o077, 0)
        saved = json.loads(item.read_text())
        self.assertEqual(saved["video_sha256"], self.sha)
        self.assertEqual(saved["youtube_video_id"], self.video_id)
        self.assertFalse(saved["publication_approved"])
        web_status, _, content = self.request("GET", "/?saved=1")
        self.assertEqual(web_status, 200)
        self.assertIn("تم حفظ الملاحظة", content.decode("utf-8"))
        self.assertIn("يحتاج تعديل", content.decode("utf-8"))

    def test_accept_private_must_assert_full_and_arabic_review(self):
        payload = self.fields(outcome="ACCEPTED_PRIVATE", notes="")
        self.assertEqual(self.request("POST", "/review", fields=payload)[0], 422)
        self.assertEqual(self.notes(), [])
        payload["full_checked"] = "yes"
        self.assertEqual(self.request("POST", "/review", fields=payload)[0], 422)
        self.assertEqual(self.notes(), [])
        payload["arabic_checked"] = "yes"
        response = self.request("POST", "/review", fields=payload)
        self.assertEqual(response[0], 303)
        self.assertEqual(self.status(), "ACCEPTED_PRIVATE_ONLY")
        self.assertFalse(json.loads(self.notes()[0].read_text())["publication_approved"])

    def test_revision_after_accept_is_allowed_but_later_accept_blocked(self):
        self.assertEqual(
            self.request("POST", "/review", fields=self.fields(
                outcome="ACCEPTED_PRIVATE", notes="",
                full_checked="yes", arabic_checked="yes"))[0], 303)
        self.assertEqual(
            self.request("POST", "/review", fields=self.fields())[0], 303)
        self.assertEqual(self.status(), "REVISION_REQUIRED_PRIVATE")
        self.assertEqual(
            self.request("POST", "/review", fields=self.fields(
                outcome="ACCEPTED_PRIVATE", notes="accepted again",
                full_checked="yes", arabic_checked="yes"))[0], 422)
        self.assertEqual(len(self.notes()), 2)

    def test_unconfirmed_upload_cannot_accept_browser_review(self):
        data = dict(self.state, state="SESSION_ACTIVE")
        _save_journal(self.journal, data)
        self.assertEqual(
            self.request("POST", "/review", fields=self.fields())[0], 422)
        self.assertEqual(self.notes(), [])

    def test_sha_tamper_before_post_cannot_write_review(self):
        self.video.write_bytes(b"tampered after private upload")
        self.assertEqual(
            self.request("POST", "/review", fields=self.fields())[0], 422)
        self.assertEqual(self.notes(), [])

    def test_wrong_journal_and_path_traversal_rejected(self):
        for name in ("../creds.json", "not-a-journal.mp4", "unknown.json"):
            self.assertEqual(
                self.request("POST", "/review", fields=self.fields(
                    journal=name))[0], 422)
        self.assertEqual(self.notes(), [])

    def test_duplicate_unexpected_and_bad_checkbox_fields_rejected(self):
        self.assertEqual(
            self.request(
                "POST", "/review", data=(
                    "csrf="+self.CSRF+"&journal=colors_v1.json"
                    "&outcome=REVISION_REQUIRED&notes=yes"
                    "&private_checked=yes&private_checked=yes"
                ).encode(), content_type="application/x-www-form-urlencoded")[0],
            422)
        self.assertEqual(self.request(
            "POST", "/review", fields=self.fields(extra_field="unknown"))[0],
            422)
        self.assertEqual(self.request(
            "POST", "/review", fields=self.fields(private_checked="no"))[0],
            422)
        self.assertEqual(self.notes(), [])

    def test_oversize_and_wrong_mime_are_rejected(self):
        self.assertEqual(self.request("POST", "/review", data=b"x"*8200,
                                      content_type="application/x-www-form-urlencoded")[0],
                         413)
        self.assertEqual(
            self.request("POST", "/review", data=b"{}",
                         content_type="application/json")[0], 415)
        self.assertEqual(self.notes(), [])

    def test_methods_paths_and_favicon_not_supported(self):
        self.assertEqual(self.request("GET", "/favicon.ico")[0], 404)
        self.assertEqual(self.request("GET", "/notes")[0], 404)
        self.assertEqual(self.request("PUT", "/review")[0], 405)
        self.assertEqual(self.request("OPTIONS", "/")[0], 405)
        self.assertEqual(self.request("DELETE", "/review")[0], 405)

    def test_browser_never_includes_a_suspicious_review_note_body(self):
        note = "<script>alert('user secret')</script>"
        self.assertEqual(
            self.request("POST", "/review", fields=self.fields(
                notes=note))[0], 303)
        status, _, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn(note.encode(), body)
        self.assertNotIn(b"<script>", body)
        self.assertEqual(self.status(), "REVISION_REQUIRED_PRIVATE")

    def test_no_insecure_public_port_option_or_weak_credentials(self):
        with self.assertRaises(ValueError):
            make_private_dashboard_handler(
                journal_root=str(self.journals),
                private_root=str(self.inbox),
                review_root=str(self.reviews),
                password="weak", csrf=self.CSRF, port=9999)
        with self.assertRaises(ValueError):
            serve_private_dashboard(
                journal_root=str(self.journals),
                private_root=str(self.inbox),
                review_root=str(self.reviews),
                port=80)

    def test_plain_render_never_shows_fake_remote_privacy_guarantee(self):
        report = build_private_draft_inbox(
            journal_root=str(self.journals), private_root=str(self.inbox),
            review_root=str(self.reviews))
        page = render_mobile_dashboard(report, csrf=self.CSRF)
        self.assertIn("ليست فحصاً مباشراً لحالة يوتيوب", page)
        self.assertNotIn("https://youtube.com", page)
        self.assertNotIn("https://studio.youtube.com", page)
        self.assertNotIn(self.video_id, page)


if __name__ == "__main__":
    unittest.main()
