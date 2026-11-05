import http.client
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from kidsstudio.dashboard_web import make_handler
from kidsstudio.studio_queue import StudioQueue


class DashboardWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "studio.sqlite"
        StudioQueue(self.db).initialize()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(str(self.db)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            conn.request(method, path)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8"), response
        finally:
            conn.close()

    def test_home_page_is_arabic_and_read_only(self):
        status, body, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("لوحة الإنتاج", body)
        self.assertIn("للقراءة فقط", body)

    def test_summary_json(self):
        status, body, _ = self.request("GET", "/api/summary")
        self.assertEqual(status, 200)
        self.assertIn('"queue_mutated": false', body)
        self.assertIn('"waiting": 0', body)

    def test_post_rejected(self):
        status, _, _ = self.request("POST", "/api/summary")
        self.assertEqual(status, 405)

    def test_unknown_path_not_found(self):
        status, _, _ = self.request("GET", "/publish")
        self.assertEqual(status, 404)

    def test_missing_database_fails_closed(self):
        self.db.unlink()
        status, body, _ = self.request("GET", "/api/summary")
        self.assertEqual(status, 503)
        self.assertIn("DASHBOARD_UNAVAILABLE", body)


if __name__ == "__main__":
    unittest.main()
