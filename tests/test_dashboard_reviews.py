import hashlib
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
from kidsstudio.video_review_history import VideoReviewHistory


class DashboardReviewsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "private"
        root.mkdir(mode=0o700)
        queue = root / "queue.sqlite"
        StudioQueue(queue).initialize()
        self.video = root / "episode.mp4"
        self.video.write_bytes(b"video fixture")
        sha = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.sha = sha
        notes_db = root / "notes.sqlite"
        notes = EpisodeNotes(notes_db)
        notes.initialize()
        notes.add(episode_id="colors_ar_01", text="راجع الصوت")
        reviews = root / "reviews.sqlite"
        history = VideoReviewHistory(reviews)
        history.initialize()
        history.record(episode_id="colors_ar_01", video_root=str(root),
                       relative_path="episode.mp4", expected_sha256=sha,
                       review_outcome="REVISION_REQUIRED", reviewer_notes="راجع الصوت")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(str(queue), notes_database=str(notes_db), reviews_database=str(reviews), video_root=str(root)))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def get(self, path, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            connection.close()

    def test_history_endpoint(self):
        status, body = self.get("/api/reviews?episode_id=colors_ar_01")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["reviews"][0]["reviewer_notes"], "راجع الصوت")
        self.assertFalse(data["owner_publication_approval"])

    def test_other_episode_empty(self):
        status, body = self.get("/api/reviews?episode_id=colors_en_01")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["reviews"], [])

    def test_history_visible_in_html(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("تاريخ مراجعات الفيديو", body)
        self.assertIn("if(true)", body)

    def test_missing_id_rejected(self):
        status, _ = self.get("/api/reviews")
        self.assertEqual(status, 503)

    def test_review_freshness_current_sha(self):
        status, body = self.get("/api/review-freshness?episode_id=colors_ar_01&current_sha256=" + self.sha)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["status"], "CURRENT_VERSION_REVISION_REQUIRED")
        self.assertTrue(data["current_sha_supplied_by_caller_not_verified"])
        self.assertFalse(data["owner_publication_approval"])

    def test_review_freshness_stale_sha(self):
        status, body = self.get("/api/review-freshness?episode_id=colors_ar_01&current_sha256=" + "b" * 64)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "LATEST_REVIEW_STALE")

    def test_combined_episode_review_endpoint(self):
        status, body = self.get("/api/episode-review?episode_id=colors_ar_01&current_sha256=" + self.sha)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["notes_unresolved"], 1)
        self.assertEqual(data["review_count"], 1)
        self.assertFalse(data["owner_publication_approval"])

    def test_combined_episode_review_rejects_missing_sha(self):
        status, _ = self.get("/api/episode-review?episode_id=colors_ar_01")
        self.assertEqual(status, 503)

    def test_verified_video_review_endpoint(self):
        status, body = self.get("/api/verified-episode-review?episode_id=colors_ar_01&relative_path=episode.mp4&expected_sha256=" + self.sha)
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["local_file_verified_at_report_time"])
        self.assertEqual(data["review_freshness"], "CURRENT_VERSION_REVISION_REQUIRED")
        self.assertFalse(data["owner_publication_approval"])

    def test_verified_video_mismatch_fails_closed(self):
        status, body = self.get("/api/verified-episode-review?episode_id=colors_ar_01&relative_path=episode.mp4&expected_sha256=" + "b" * 64)
        self.assertEqual(status, 503)
        self.assertFalse(json.loads(body)["owner_publication_approval"])

    def test_verified_video_form_visible(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("فحص نسخة الفيديو الحالية", body)
        self.assertIn("if(true)", body)
        self.assertIn("data.video_bytes_verified", body)

    def test_post_rejected(self):
        status, _ = self.get("/api/reviews?episode_id=colors_ar_01", "POST")
        self.assertEqual(status, 405)


if __name__ == "__main__":
    unittest.main()
