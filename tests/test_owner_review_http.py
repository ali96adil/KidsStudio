"""Integration tests for loopback review server using a real HTTP client."""
import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode
from http.server import ThreadingHTTPServer

from kidsstudio.owner_review_store import OwnerReviewStore
from kidsstudio.owner_review_web import make_handler


class ReviewHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.video = root / "red.mp4"
        self.video.write_bytes(b"0123456789")
        self.store = OwnerReviewStore(root / "reviews.sqlite")
        self.store.initialize()
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.store, "secret-token", "red", self.video)
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_video_range(self):
        code, headers, body = self.request("GET", "/video", headers={"Range": "bytes=2-5"})
        self.assertEqual(code, 206)
        self.assertEqual(body, b"2345")
        self.assertEqual(headers["Content-Range"], "bytes 2-5/10")

    def test_invalid_range(self):
        code, headers, body = self.request("GET", "/video", headers={"Range": "bytes=99-"})
        self.assertEqual(code, 416)
        self.assertEqual(headers["Content-Range"], "bytes */10")

    def test_form_and_record(self):
        code, _, body = self.request("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b'src="/video"', body)
        form = urlencode({"token": "secret-token", "episode": "red", "state": "changes_requested", "note": "Fix audio"})
        code, _, _ = self.request("POST", "/review", body=form, headers={
            "Content-Type": "application/x-www-form-urlencoded"
        })
        self.assertEqual(code, 200)
        self.assertEqual(self.store.latest()["red"]["note"], "Fix audio")

    def test_reject_wrong_token(self):
        form = urlencode({"token": "bad", "episode": "red", "state": "approved", "note": "No"})
        code, _, _ = self.request("POST", "/review", body=form, headers={
            "Content-Type": "application/x-www-form-urlencoded"
        })
        self.assertEqual(code, 400)
        self.assertEqual(self.store.latest(), {})


if __name__ == "__main__":
    unittest.main()
