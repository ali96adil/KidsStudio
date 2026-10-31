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
