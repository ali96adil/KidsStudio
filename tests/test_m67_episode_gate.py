"""M67 first-episode storyboard tests."""
import copy
import json
from pathlib import Path
import unittest

from kidsstudio.m67_episode_gate import validate_episode, EpisodeGateError


ROOT = Path(__file__).resolve().parents[1]


class M67EpisodeGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(
            (ROOT / "examples/m67_colors_red_episode_001.json").read_text(
                encoding="utf-8"))

    def test_first_episode_draft_is_valid(self):
        result = validate_episode(self.data)
        self.assertEqual(result["status"], "STORYBOARD_VALID_DRAFT_ONLY")
        self.assertFalse(result["upload_authorized"])

    def test_public_visibility_rejected(self):
        data = copy.deepcopy(self.data)
        data["youtube_visibility"] = "PUBLIC"
        with self.assertRaises(EpisodeGateError):
            validate_episode(data)

    def test_timeline_gap_rejected(self):
        data = copy.deepcopy(self.data)
        data["beats"][1]["start"] += 1
        with self.assertRaises(EpisodeGateError):
            validate_episode(data)

    def test_no_recall_rejected(self):
        data = copy.deepcopy(self.data)
        for beat in data["beats"]:
            if beat["purpose"] == "recall":
                beat["purpose"] = "decorative"
        with self.assertRaises(EpisodeGateError):
            validate_episode(data)

    def test_external_link_requirement_rejected(self):
        data = copy.deepcopy(self.data)
        data["qa_requirements"]["no_external_links_or_qr"] = False
        with self.assertRaises(EpisodeGateError):
            validate_episode(data)


if __name__ == "__main__":
    unittest.main()
