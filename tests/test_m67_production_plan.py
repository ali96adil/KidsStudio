"""M67 production planning contract tests."""
import json
from pathlib import Path
import unittest

from kidsstudio.m67_production_plan import compile_plan

ROOT = Path(__file__).resolve().parents[1]


class M67ProductionPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(
            (ROOT / "examples/m67_colors_red_episode_001.json").read_text(
                encoding="utf-8"))

    def test_godot_beats_match_storyboard(self):
        plan = compile_plan(self.storyboard)
        scene = plan["godot_scene_spec"]
        self.assertEqual(scene["duration_seconds"], 75)
        self.assertEqual(scene["fps"], 30)
        self.assertEqual(scene["beats"][0]["motion"], "wave_right")
        self.assertEqual(scene["beats"][-1]["end"], 75)
        self.assertEqual(len(scene["beats"]), 6)

    def test_voice_segments_not_fabricated(self):
        plan = compile_plan(self.storyboard)
        self.assertTrue(all(segment["recording_status"] == "NOT_RECORDED"
                            for segment in plan["voice_segments"]))
        self.assertFalse(plan["audio_generated"])

    def test_no_upload_or_publication(self):
        plan = compile_plan(self.storyboard)
        self.assertFalse(plan["youtube_upload_authorized"])
        self.assertFalse(plan["public_release_authorized"])
        self.assertFalse(plan["rendered"])

    def test_unsupported_fps_rejected(self):
        with self.assertRaises(ValueError):
            compile_plan(self.storyboard, fps=60)


if __name__ == "__main__":
    unittest.main()
