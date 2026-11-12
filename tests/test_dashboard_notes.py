import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from kidsstudio.dashboard_web import make_handler
from kidsstudio.episode_notes import EpisodeNotes
from kidsstudio.studio_queue import StudioQueue


class DashboardNotesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "private"
        root.mkdir(mode=0o700)
        self.queue_db = root / "queue.sqlite"
        StudioQueue(self.queue_db).initialize()
        self.notes_db = root / "notes.sqlite"
        self.notes = EpisodeNotes(self.notes_db)
        self.notes.initialize()
        self.notes.add(episode_id="colors_ar_01", text="راجع صوت الأرنب")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(str(self.queue_db), str(self.notes_db)))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            connection.close()

    def test_notes_ui_visible_when_enabled(self):
        status, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("ملاحظات الحلقات", body)
        self.assertIn("if(true)", body)
        self.assertIn("textContent=note.text", body)

    def test_episode_notes_are_readable(self):
        status, body = self.request("GET", "/api/notes?episode_id=colors_ar_01")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["notes"][0]["text"], "راجع صوت الأرنب")
        self.assertFalse(data["publication_approved"])

    def test_other_episode_isolated(self):
        status, body = self.request("GET", "/api/notes?episode_id=colors_en_01")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["notes"], [])

    def test_missing_episode_fails_closed(self):
        status, _ = self.request("GET", "/api/notes")
        self.assertEqual(status, 503)

    def test_invalid_episode_fails_closed(self):
        status, _ = self.request("GET", "/api/notes?episode_id=..%2Fother")
        self.assertEqual(status, 503)

    def test_write_method_rejected(self):
        status, _ = self.request("POST", "/api/notes?episode_id=colors_ar_01")
        self.assertEqual(status, 405)


if __name__ == "__main__":
    unittest.main()
