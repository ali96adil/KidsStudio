"""M68 source-reuse and safe-release planning tests."""
import json
from pathlib import Path
import unittest

from kidsstudio.m68_shorts_plan import derive, ShortsPlanError


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/m67_colors_red_episode_001.json"


class ShortsPlanningTests(unittest.TestCase):
    def test_derive_from_existing_assets(self):
        source = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        result = derive(source)
        self.assertEqual(len(result["shorts"]), 3)
        self.assertEqual([s["source_beats"][0] for s in result["shorts"]], [2, 3, 4])
        for short in result["shorts"]:
            self.assertEqual(short["render"]["width"], 1080)
            self.assertEqual(short["render"]["height"], 1920)
            self.assertEqual(short["youtube_visibility"], "PRIVATE_ONLY")
            self.assertFalse(short["youtube_upload_authorized"])
            self.assertFalse(short["public_release_authorized"])
            self.assertEqual(len(short["source_asset_keys"]), 2)

    def test_no_suitable_beat_does_not_force_short(self):
        source = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        for beat in source["beats"]:
            beat["purpose"] = "greeting"
        self.assertEqual(derive(source)["status"], "NO_SUITABLE_SHORTS")

    def test_bad_timing_rejected(self):
        source = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        source["beats"][0]["end"] = source["beats"][0]["start"]
        with self.assertRaises(ShortsPlanError):
            derive(source)
