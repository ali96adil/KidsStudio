"""Tests for local script rewrite proposal integrity."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from kidsstudio.m68_local_script_rewriter import (
    propose_revision, RevisionModelError)


class FakeRewriter:
    def rewrite(self, *, script, lesson, issues):
        return {"revised_script": script + "\nWhat did we learn today?",
                "change_summary": "Added a clear learning assessment at the end."}


class ScriptRewriterTests(unittest.TestCase):
    def test_writes_new_file_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / "script.txt"
            lesson = root / "lesson.json"
            output = root / "revised.txt"
            script.write_text("Learn colors.", encoding="utf-8")
            lesson.write_text(json.dumps({"learning_objective": "colors"}))
            original = script.read_bytes()
            state = {"status": "REVISION_TASK_READY",
                     "current_script_sha256": hashlib.sha256(original).hexdigest(),
                     "attempts": [], "attempt_number": 1,
                     "original_script_sha256": hashlib.sha256(original).hexdigest(),
                     "short_id": "s", "source_episode_id": "e",
                     "video_sha256": "f" * 64,
                     "issues": [{"axis": "pedagogy"}]}
            result = propose_revision(
                state, script_path=script, lesson_path=lesson,
                output_path=output, rewriter=FakeRewriter())
            self.assertEqual(script.read_bytes(), original)
            self.assertTrue(output.is_file())
            self.assertEqual(result["lifecycle"]["status"], "REVISION_AWAITING_REVIEW")
            self.assertFalse(result["public_release_authorized"])
            with self.assertRaises(FileExistsError):
                propose_revision(state, script_path=script, lesson_path=lesson,
                                 output_path=output, rewriter=FakeRewriter())

    def test_rejects_changed_script(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / "script.txt"
            lesson = root / "lesson.json"
            script.write_text("New script", encoding="utf-8")
            lesson.write_text("{}")
            with self.assertRaises(RevisionModelError):
                propose_revision({"status": "REVISION_TASK_READY",
                                  "current_script_sha256": "a" * 64},
                                 script_path=script, lesson_path=lesson,
                                 output_path=root / "out.txt",
                                 rewriter=FakeRewriter())
