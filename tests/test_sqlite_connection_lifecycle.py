"""Regression coverage for SQLite handles used by persistent local records."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from kidsstudio.episode_notes import EpisodeNotes
from kidsstudio.media_worker import MediaJournal
from kidsstudio.video_review_history import VideoReviewHistory


class _TrackedConnection:
    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self.closed = False

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, *args):
        return self._connection.__exit__(*args)

    def close(self):
        self.closed = True
        self._connection.close()


class ConnectionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self._real_connect = sqlite3.connect

    def tracker(self):
        opened: list[_TrackedConnection] = []

        def connect(*args, **kwargs):
            item = _TrackedConnection(self._real_connect(*args, **kwargs))
            opened.append(item)
            return item

        return opened, connect

    def test_episode_notes_closes_initialize_write_and_read_connections(self):
        opened, connect = self.tracker()
        with patch("kidsstudio.episode_notes.sqlite3.connect", side_effect=connect):
            notes = EpisodeNotes(self.root / "notes.sqlite")
            notes.initialize()
            note_id = notes.add(episode_id="colors_ar_01", text="check voice")
            self.assertEqual(notes.list_notes(episode_id="colors_ar_01")[0]["note_id"],
                             note_id)
            notes.resolve(episode_id="colors_ar_01", note_id=note_id)
        self.assertTrue(opened)
        self.assertTrue(all(item.closed for item in opened))

    def test_video_history_closes_initialize_write_and_read_connections(self):
        video_root = self.root / "videos"
        video_root.mkdir(mode=0o700)
        video = video_root / "colors.mp4"
        video.write_bytes(b"private-test-video")
        os.chmod(video, 0o600)
        digest = hashlib.sha256(video.read_bytes()).hexdigest()
        opened, connect = self.tracker()
        with patch("kidsstudio.video_review_history.sqlite3.connect",
                   side_effect=connect):
            history = VideoReviewHistory(self.root / "reviews.sqlite")
            history.initialize()
            history.record(
                episode_id="colors_ar_01", video_root=str(video_root),
                relative_path=video.name, expected_sha256=digest,
                reviewer_notes="private test", review_outcome="NEEDS_REVIEW")
            self.assertEqual(len(history.list_reviews(episode_id="colors_ar_01")), 1)
        self.assertTrue(opened)
        self.assertTrue(all(item.closed for item in opened))

    def test_media_journal_closes_initialize_begin_and_done_connections(self):
        opened, connect = self.tracker()
        with patch("kidsstudio.media_worker.sqlite3.connect", side_effect=connect):
            journal = MediaJournal(self.root / "media.sqlite")
            job_id = "1" * 32
            request_sha = "2" * 64
            state, prior = journal.begin(
                job_id, request_sha, "godot_render", "colors_preview")
            self.assertEqual((state, prior), ("NEW", None))
            journal.done(job_id, {"status": "done"})
        self.assertTrue(opened)
        self.assertTrue(all(item.closed for item in opened))


if __name__ == "__main__":
    unittest.main()
