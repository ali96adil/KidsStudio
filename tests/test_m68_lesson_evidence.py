"""Tests for M68 lesson evidence integrity and conservative review scope."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m68_lesson_evidence import audit_lesson


class LessonEvidenceTests(unittest.TestCase):
    def test_documented_lesson_never_claims_educational_certification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "script.txt"
            script.write_text("أحمر، أزرق، أصفر", encoding="utf-8")
            lesson = root / "lesson.json"
            handoff = {"short_id": "short1", "source_episode_id": "episode1",
                       "sha256": "a" * 64}
            doc = {
                "schema_version": 1, "short_id": "short1",
                "source_episode_id": "episode1", "video_sha256": "a" * 64,
                "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                "language": "ar", "learning_objective": "Identify three colors",
                "age_range": "Ages three to five",
                "teaching_method": "Repeat and point to colored objects",
                "assessment_question": "Which of these objects is red?",
                "fact_check_reference": "Owner-approved color curriculum",
            }
            lesson.write_text(json.dumps(doc))
            result = audit_lesson(handoff, script_path=script, lesson_path=lesson)
            self.assertEqual(result["reasons"], [])
            self.assertFalse(result["pedagogy_independently_verified"])
            self.assertFalse(result["youtube_upload_authorized"])
            script.write_text("changed script")
            result = audit_lesson(handoff, script_path=script, lesson_path=lesson)
            self.assertIn("script_sha256_mismatch", result["reasons"])

    def test_missing_objective_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "script.txt"
            script.write_text("Learn colors")
            lesson = root / "lesson.json"
            lesson.write_text(json.dumps({"schema_version": 1}))
            result = audit_lesson({"short_id": "short1", "sha256": "a" * 64}, script_path=script,
                                  lesson_path=lesson)
            self.assertIn("learning_objective_missing", result["reasons"])

    def test_unpinned_video_identity_rejected(self):
        with self.assertRaises(ValueError):
            audit_lesson({"short_id": "short1", "sha256": "untrusted"},
                         script_path="/tmp/not-present",
                         lesson_path="/tmp/not-present")
