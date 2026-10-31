"""Conservative local two-model readiness qualification tests."""
import unittest

from kidsstudio.m68_lesson_model_readiness import qualify


class LessonModelReadinessTests(unittest.TestCase):
    def setUp(self):
        self.args = dict(first_endpoint="http://127.0.0.1:11434/api/chat",
                         first_model="model-a",
                         second_endpoint="http://127.0.0.1:11435/api/chat",
                         second_model="model-b")

    def test_both_installed_only_allows_inference_attempt(self):
        def inspect(endpoint):
            return {"reachable": True, "models": ["model-a", "model-b"]}
        result = qualify(**self.args, inspector=inspect)
        self.assertTrue(result["ready_for_inference_attempt"])
        self.assertFalse(result["model_inference_executed"])
        self.assertFalse(result["youtube_upload_authorized"])

    def test_missing_model_blocks(self):
        result = qualify(**self.args, inspector=lambda _: {
            "reachable": True, "models": ["model-a"]})
        self.assertFalse(result["ready_for_inference_attempt"])

    def test_unreachable_service_blocks(self):
        result = qualify(**self.args, inspector=lambda _: {
            "reachable": False, "models": []})
        self.assertFalse(result["ready_for_inference_attempt"])

    def test_same_model_rejected(self):
        self.args["second_model"] = "model-a"
        with self.assertRaises(ValueError):
            qualify(**self.args, inspector=lambda _: {
                "reachable": True, "models": ["model-a"]})

    def test_same_endpoint_rejected(self):
        self.args["second_endpoint"] = self.args["first_endpoint"]
        with self.assertRaises(ValueError):
            qualify(**self.args, inspector=lambda _: {
                "reachable": True, "models": ["model-a", "model-b"]})
