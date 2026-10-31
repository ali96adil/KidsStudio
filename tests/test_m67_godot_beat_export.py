"""M67 Godot beat export contract tests."""
import json
from pathlib import Path
import tempfile
import unittest

from kidsstudio.m67_godot_beat_export import split_beats, export_beats, BeatExportError

ROOT = Path(__file__).resolve().parents[1]


class M67GodotBeatExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = json.loads(
            (ROOT / "examples/m67_colors_red_episode_001.json").read_text(
                encoding="utf-8"))

    def test_six_valid_local_timelines(self):
        beats = split_beats(self.storyboard)
        self.assertEqual(len(beats), 6)
        self.assertEqual(sum(x["scene"]["duration_seconds"] for x in beats), 75)
        self.assertTrue(all(x["scene"]["beats"][0]["start"] == 0 for x in beats))
        self.assertTrue(all(x["render_status"] == "NOT_RENDERED" for x in beats))

    def test_export_creates_only_plans(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "beat_plans"
            report = export_beats(self.storyboard, out)
            self.assertEqual(report["status"], "GODOT_BEAT_PLANS_READY_NOT_RENDERED")
            self.assertEqual(len(list(out.glob("beat_*_scene.json"))), 6)
            self.assertFalse(report["youtube_upload_authorized"])

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BeatExportError):
                export_beats(self.storyboard, Path(tmp))


if __name__ == "__main__":
    unittest.main()
