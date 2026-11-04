import json
import unittest

from kidsstudio.mcp_server import handle
from kidsstudio.openmontage_pipeline_bridge import PIPELINES, plan_episode


class PipelinePlannerTests(unittest.TestCase):
    def test_animated_pipeline_has_safety_and_owner_gates(self):
        plan = plan_episode(episode_id="colors_001", topic="The colors",
                            available_engines=["godot"])
        self.assertEqual(plan["status"], "PLAN_ONLY_NOT_EXECUTED")
        self.assertIn("child_safety_review", plan["stages"])
        self.assertIn("private_owner_review", plan["stages"])
        self.assertIn("godot", plan["available_recommended_engines"])
        self.assertFalse(plan["youtube_uploaded"])
        self.assertFalse(plan["public_release_authorized"])

    def test_all_pipelines_have_private_owner_review(self):
        for kind in PIPELINES:
            with self.subTest(kind=kind):
                plan = plan_episode(episode_id="test", topic="Numbers", kind=kind)
                self.assertIn("private_owner_review", plan["stages"])

    def test_reject_unknown_pipeline_language_and_invalid_engines(self):
        for kwargs in ({"kind": "public_upload"}, {"language": "xx"},
                       {"available_engines": ["godot", 1]}, {"topic": ""}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                plan_episode(**{"episode_id": "test", "topic": "Numbers", **kwargs})

    def test_mcp_exposes_plan_and_rejects_execution(self):
        def call(name, arguments):
            return handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                           "params": {"name": name, "arguments": arguments}})["result"]
        plan = call("kidsstudio_plan_episode",
                    {"episode_id": "colors_001", "topic": "Colors", "language": "ar"})
        self.assertFalse(plan["isError"])
        payload = json.loads(plan["content"][0]["text"])
        self.assertEqual(payload["pipeline"], "animated_explainer")
        self.assertTrue(call("kidsstudio_execute_episode", {})["isError"])


if __name__ == "__main__":
    unittest.main()
