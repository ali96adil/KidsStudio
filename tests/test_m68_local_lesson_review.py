"""M68 actual local lesson model response validation and fail-closed identity tests."""
import json
import unittest
from unittest.mock import patch

from kidsstudio.m68_local_lesson_review import OllamaLesson, LessonModelError, review_lesson


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _):
        checks = {axis: {"decision": "PASS",
                         "evidence": "The supplied script follows the lesson objective explicitly."}
                  for axis in ("pedagogy", "source_consistency")}
        return json.dumps({"done": True, "message": {
            "content": json.dumps({"checks": checks,
                                    "summary": "Both lesson checks have specific script evidence."})}}).encode()


class FakeOpener:
    def open(self, req, timeout):
        assert req.full_url.startswith("http://127.0.0.1:")
        return FakeResponse()


class LessonModelTests(unittest.TestCase):
    def test_real_json_transport_contract(self):
        reviewer = OllamaLesson("http://127.0.0.1:11434/api/chat",
                                "lesson-model-1", opener=FakeOpener())
        answer, digest = reviewer.run(
            script="This lesson teaches colors to preschool children.",
            lesson={"learning_objective": "Name colors"})
        self.assertEqual(answer["checks"]["pedagogy"]["decision"], "PASS")
        self.assertEqual(len(digest), 64)

    def test_duplicate_model_endpoint_rejected(self):
        first = OllamaLesson("http://127.0.0.1:11434/api/chat", "model-one")
        second = OllamaLesson("http://127.0.0.1:11434/api/chat", "model-two")
        with self.assertRaises(LessonModelError):
            review_lesson({"sha256": "a" * 64}, script_path="/tmp/unused",
                          lesson_path="/tmp/unused", first=first, second=second)

    def test_malformed_response_rejected(self):
        class BadResponse(FakeResponse):
            def read(self, _):
                return b'{"done":true,"message":{"content":"{}"}}'
        class BadOpener:
            def open(self, *_args, **_kwargs):
                return BadResponse()
        reviewer = OllamaLesson("http://127.0.0.1:11434/api/chat",
                                "lesson-model-1", opener=BadOpener())
        with self.assertRaises(LessonModelError):
            reviewer.run(script="Learn colors", lesson={})

    def test_changed_source_after_model_review_rejected(self):
        from unittest.mock import patch
        from kidsstudio.m68_local_lesson_review import review_lesson
        first = OllamaLesson("http://127.0.0.1:11434/api/chat", "model-one")
        second = OllamaLesson("http://127.0.0.1:11435/api/chat", "model-two")
        first.run = lambda **kwargs: ({"checks": {
            "pedagogy": {"decision": "PASS", "evidence": "This lesson demonstrates a clear learning objective."},
            "source_consistency": {"decision": "PASS", "evidence": "The script and lesson plan contain the same color examples."}}, "summary": "The lesson is aligned with its declared learning objective."}, "c" * 64)
        second.run = first.run
        with patch("kidsstudio.m68_local_lesson_review.audit_lesson",
                   side_effect=[
                       {"reasons": [], "script_sha256": "a" * 64},
                       {"reasons": ["script_sha256_mismatch"], "script_sha256": "b" * 64}
                   ]), patch("pathlib.Path.read_text", side_effect=[
                       "Learn three colors", '{"learning_objective":"Learn colors"}'
                   ]):
            with self.assertRaises(LessonModelError):
                review_lesson({"short_id": "s", "source_episode_id": "e",
                               "sha256": "f" * 64},
                              script_path="/tmp/script.txt", lesson_path="/tmp/lesson.json",
                              first=first, second=second)

    def test_two_models_agree_or_disagree_without_upload_permission(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from kidsstudio.m68_lesson_evidence import audit_lesson

        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "script.txt"
            lesson = Path(directory) / "lesson.json"
            script.write_text("Today we identify the red, blue and yellow colors.",
                              encoding="utf-8")
            handoff = {"short_id": "short-1", "source_episode_id": "episode-1",
                       "sha256": "f" * 64}
            doc = {
                "schema_version": 1, "short_id": "short-1",
                "source_episode_id": "episode-1", "video_sha256": "f" * 64,
                "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                "language": "en", "learning_objective": "Identify three colors",
                "age_range": "Children three to five years old",
                "teaching_method": "Name and point at each color",
                "assessment_question": "Which object is the red one?",
                "fact_check_reference": "Owner approved color curriculum",
            }
            lesson.write_text(json.dumps(doc), encoding="utf-8")
            self.assertFalse(audit_lesson(handoff, script_path=script,
                                          lesson_path=lesson)["reasons"])
            first = OllamaLesson("http://127.0.0.1:11434/api/chat", "model-one")
            second = OllamaLesson("http://127.0.0.1:11435/api/chat", "model-two")
            def response(decision):
                return {"checks": {
                    axis: {"decision": decision,
                           "evidence": "The script explicitly names three colors and asks a question."}
                    for axis in ("pedagogy", "source_consistency")}}
            first.run = lambda **kwargs: (response("PASS"), "a" * 64)
            second.run = lambda **kwargs: (response("PASS"), "b" * 64)
            approved = review_lesson(handoff, script_path=script, lesson_path=lesson,
                                     first=first, second=second)
            self.assertTrue(approved["checks"]["pedagogy"])
            self.assertFalse(approved["youtube_upload_authorized"])
            second.run = lambda **kwargs: (response("UNSURE"), "c" * 64)
            uncertain = review_lesson(handoff, script_path=script, lesson_path=lesson,
                                      first=first, second=second)
            self.assertFalse(uncertain["checks"]["pedagogy"])
            self.assertFalse(uncertain["checks"]["source_consistency"])
            self.assertFalse(uncertain["public_release_authorized"])
