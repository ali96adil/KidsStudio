"""Tests for bounded educational revision attempts."""
import unittest

from kidsstudio.m68_lesson_revision_lifecycle import (
    MAX_ATTEMPTS, start_revision, record_revision)


class RevisionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.task = {"status": "LESSON_REVISION_REQUIRED",
                     "short_id": "s", "source_episode_id": "e",
                     "video_sha256": "f" * 64,
                     "script_sha256": "a" * 64,
                     "assigned_role": "script_revision_agent",
                     "issues": [{"axis": "pedagogy", "decision": "UNSURE"}],
                     "youtube_upload_authorized": False,
                     "public_release_authorized": False}

    def test_requires_changed_script_hash(self):
        state = start_revision(self.task)
        with self.assertRaises(ValueError):
            record_revision(state, revised_script_sha256="a" * 64)

    def test_three_attempts_then_triage(self):
        previous = None
        for i, char in enumerate(("b", "c", "d"), start=1):
            state = start_revision(self.task, previous=previous)
            self.assertEqual(state["attempt_number"], i)
            previous = record_revision(state, revised_script_sha256=char * 64)
            self.task["script_sha256"] = char * 64
        blocked = start_revision(self.task, previous=previous)
        self.assertEqual(blocked["status"], "REVISION_LIMIT_REACHED")
        self.assertTrue(blocked["requires_manual_triage"])
        self.assertEqual(len(blocked["attempts"]), MAX_ATTEMPTS)
        self.assertFalse(blocked["youtube_upload_authorized"])

    def test_cannot_retry_other_episode(self):
        previous = record_revision(start_revision(self.task),
                                   revised_script_sha256="b" * 64)
        self.task["source_episode_id"] = "other"
        self.task["script_sha256"] = "b" * 64
        with self.assertRaises(ValueError):
            start_revision(self.task, previous=previous)
